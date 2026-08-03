import json
import gc
import threading
from typing import Generator
from tpgk.logging_utils import get_logger

# `requests` (and its urllib3/chardet dependency chain) takes ~140ms to import,
# a large share of app startup. Since AI chat is opt-in, defer it until first use.
_requests = None
logger = get_logger(__name__)


class AIRequestCancelled(Exception):
    """Raised when the user cancels a streaming AI request."""


def _requests_module():
    global _requests
    if _requests is None:
        import requests
        _requests = requests
    return _requests


class AIClient:
    PROVIDERS = {
        "openai": {
            "name": "OpenAI", "url": "https://api.openai.com/v1/chat/completions",
            "default_model": "gpt-4o", "protocol": "openai",
        },
        "claude": {
            "name": "Claude (Anthropic)", "url": "https://api.anthropic.com/v1/messages",
            # Fix #18: update to current model
            "default_model": "claude-sonnet-4-6", "protocol": "claude",
        },
        "gemini": {
            "name": "Google Gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
            "default_model": "gemini-2.5-flash", "protocol": "gemini",
        },
        "deepseek": {
            "name": "DeepSeek", "url": "https://api.deepseek.com/chat/completions",
            "default_model": "deepseek-chat", "protocol": "openai",
        },
        "ollama": {
            "name": "Ollama (Local)", "url": "http://localhost:11434/v1/chat/completions",
            "default_model": "llama3", "protocol": "ollama",
        },
        "custom": {
            "name": "Custom OpenAI API", "url": "http://localhost:8080/v1/chat/completions",
            "default_model": "llama3", "protocol": "openai",
        },
    }

    MAX_MESSAGE_PAIRS = 20

    def __init__(self, provider: str, api_key: str = "", model: str = None, base_url: str = ""):
        self.provider = provider
        self.api_key = api_key
        info = self.PROVIDERS[provider]
        self.model = model or info["default_model"]
        self.base_url = base_url or info["url"]
        self._protocol = info["protocol"]
        self._messages = []
        self._system_prompt = ""
        self._active_response = None
        self._response_lock = threading.Lock()

    def _truncate_messages(self):
        system_msgs = [m for m in self._messages if m.get("role") == "system"]
        non_system = [m for m in self._messages if m.get("role") != "system"]
        if len(non_system) > self.MAX_MESSAGE_PAIRS * 2:
            non_system = non_system[-(self.MAX_MESSAGE_PAIRS * 2):]
            self._messages = system_msgs + non_system

    def set_system_prompt(self, prompt: str):
        self._system_prompt = prompt

    def chat(self, message: str) -> str:
        self._truncate_messages()
        has_system = any(m.get("role") == "system" for m in self._messages)
        if self._system_prompt and not has_system:
            self._messages.insert(0, {"role": "system", "content": self._system_prompt})
        self._messages.append({"role": "user", "content": message})
        try:
            if self._protocol == "claude":
                return self._call_claude()
            elif self._protocol == "gemini":
                return self._call_gemini(message)
            else:
                return self._call_openai_compatible()
        except Exception:
            self._messages.pop()
            if self._system_prompt and not has_system and self._messages and self._messages[0].get("role") == "system":
                self._messages.pop(0)
            raise

    def chat_stream(self, message: str, cancel_event=None) -> Generator[str, None, None]:
        self._truncate_messages()
        has_system = any(m.get("role") == "system" for m in self._messages)
        if self._system_prompt and not has_system:
            self._messages.insert(0, {"role": "system", "content": self._system_prompt})
        self._messages.append({"role": "user", "content": message})
        try:
            if self._protocol == "claude":
                yield from self._call_claude_stream(cancel_event)
            elif self._protocol == "gemini":
                yield from self._call_gemini_stream(message, cancel_event)
            else:
                yield from self._call_openai_stream(cancel_event)
        except Exception:
            self._messages.pop()
            if self._system_prompt and not has_system and self._messages and self._messages[0].get("role") == "system":
                self._messages.pop(0)
            raise

    def reset(self):
        self._messages = []
        gc.collect()

    def cancel(self):
        """Close the current response so a streaming worker can exit promptly."""
        with self._response_lock:
            response = self._active_response
            self._active_response = None
        if response is not None:
            response.close()

    def _check_cancelled(self, cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            self.cancel()
            raise AIRequestCancelled()

    def _open_stream(self, cancel_event, *args, **kwargs):
        self._check_cancelled(cancel_event)
        try:
            response = _requests_module().post(*args, **kwargs, stream=True, timeout=(10, 5))
        except Exception:
            self._check_cancelled(cancel_event)
            raise
        with self._response_lock:
            self._active_response = response
        self._check_cancelled(cancel_event)
        try:
            response.raise_for_status()
        except Exception:
            self._close_stream(response)
            raise
        return response

    def _close_stream(self, response):
        with self._response_lock:
            if self._active_response is response:
                self._active_response = None
        response.close()

    def _call_openai_compatible(self) -> str:
        requests = _requests_module()
        headers = {"Content-Type": "application/json"}
        if self.api_key and self._protocol != "ollama":
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": self._messages}
        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        self._messages.append({"role": "assistant", "content": content})
        return content

    def _call_openai_stream(self, cancel_event=None) -> Generator[str, None, None]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self._protocol != "ollama":
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": self._messages, "stream": True}
        resp = self._open_stream(cancel_event, self.base_url, headers=headers, json=payload)
        resp.encoding = 'utf-8'
        full = ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                self._check_cancelled(cancel_event)
                if not line or line.startswith(":") or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full += content
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
            self._check_cancelled(cancel_event)
            self._messages.append({"role": "assistant", "content": full})
        finally:
            self._close_stream(resp)

    def _call_claude(self) -> str:
        requests = _requests_module()
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        system = ""
        msgs = []
        for m in self._messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)
        payload = {"model": self.model, "max_tokens": 8192, "messages": msgs}
        if system:
            payload["system"] = system
        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        self._messages.append({"role": "assistant", "content": content})
        return content

    def _call_claude_stream(self, cancel_event=None) -> Generator[str, None, None]:
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        system = ""
        msgs = []
        for m in self._messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                msgs.append(m)
        payload = {"model": self.model, "max_tokens": 8192, "messages": msgs, "stream": True}
        if system:
            payload["system"] = system
        resp = self._open_stream(cancel_event, self.base_url, headers=headers, json=payload)
        full = ""
        event_type = ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                self._check_cancelled(cancel_event)
                if not line:
                    event_type = ""
                    continue
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if event_type == "error":
                    try:
                        err = json.loads(data_str)
                        raise RuntimeError(err.get("error", {}).get("message", data_str))
                    except (json.JSONDecodeError, KeyError):
                        raise RuntimeError(data_str)
                try:
                    event = json.loads(data_str)
                    if event.get("type") == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            full += text
                            yield text
                    elif event.get("type") == "message_stop":
                        break
                    elif event.get("type") == "error":
                        raise RuntimeError(event.get("error", {}).get("message", str(event)))
                except (json.JSONDecodeError, KeyError):
                    continue
            self._check_cancelled(cancel_event)
            self._messages.append({"role": "assistant", "content": full})
        finally:
            self._close_stream(resp)

    def _call_gemini(self, message: str) -> str:
        requests = _requests_module()
        url = self.base_url.replace("{model}", self.model)
        # Use non-streaming endpoint for the non-streaming variant
        url = url.replace(":streamGenerateContent", ":generateContent")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        contents = []
        for m in self._messages:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            })
        payload = {"contents": contents, "generationConfig": {
            "temperature": 0.7, "maxOutputTokens": 8192,
        }}
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        self._messages.append({"role": "assistant", "content": content})
        return content

    def _call_gemini_stream(self, message: str, cancel_event=None) -> Generator[str, None, None]:
        # Fix #19: real SSE streaming via streamGenerateContent?alt=sse
        url = self.base_url.replace("{model}", self.model)
        if ":streamGenerateContent" not in url:
            url = url.replace(":generateContent", ":streamGenerateContent")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        params = {"alt": "sse"}
        contents = []
        for m in self._messages:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            })
        payload = {"contents": contents, "generationConfig": {
            "temperature": 0.7, "maxOutputTokens": 8192,
        }}
        resp = self._open_stream(cancel_event, url, headers=headers, params=params, json=payload)
        full = ""
        try:
            for line in resp.iter_lines(decode_unicode=True):
                self._check_cancelled(cancel_event)
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                    text = event["candidates"][0]["content"]["parts"][0]["text"]
                    if text:
                        full += text
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
            self._check_cancelled(cancel_event)
            self._messages.append({"role": "assistant", "content": full})
        finally:
            self._close_stream(resp)

    @staticmethod
    def fetch_models(provider: str, api_key: str = "", base_url: str = ""):
        requests = _requests_module()
        try:
            if provider == "ollama":
                url = base_url.replace("/v1/chat/completions", "").rstrip("/") if base_url else "http://localhost:11434"
                url = url.rstrip("/") + "/api/tags"
                resp = requests.get(url, timeout=5)
                data = resp.json()
                return [m.get("name", m.get("model", str(m)))
                        for m in data.get("models", [])]
            elif provider == "custom" and base_url:
                base = base_url.rsplit("/chat/completions", 1)[0].rstrip("/")
                if not base:
                    base = base_url.rstrip("/")
                url = f"{base}/models"
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = requests.get(url, headers=headers, timeout=5)
                data = resp.json()
                return [m.get("id", m.get("name", str(m)))
                        for m in data.get("data", [])]
            elif provider in ("openai", "deepseek") and api_key:
                # Fix #20: OpenAI and DeepSeek both expose GET /v1/models in the same format
                info = AIClient.PROVIDERS[provider]
                base = info["url"].rsplit("/chat/completions", 1)[0].rstrip("/")
                url = f"{base}/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    return sorted([m.get("id", str(m)) for m in data.get("data", [])])
        except Exception:
            logger.exception("ai_models_fetch_failed provider=%s", provider)
        return []

    @staticmethod
    def ping_provider(provider: str, url: str) -> bool:
        requests = _requests_module()
        try:
            if provider == "ollama":
                u = url.replace("/v1/chat/completions", "").rstrip("/") if url else "http://localhost:11434"
                r = requests.get(f"{u}/api/tags", timeout=3)
                return r.status_code == 200
            elif provider == "custom" and url:
                base = url.rsplit("/chat/completions", 1)[0].rstrip("/")
                if not base:
                    base = url.rstrip("/")
                for test_url in [url, f"{base}/models", base]:
                    try:
                        r = requests.get(test_url, timeout=3)
                        if r.status_code == 200:
                            return True
                    except Exception:
                        logger.debug("ai_provider_ping_attempt_failed provider=%s", provider,
                                     exc_info=True)
                        continue
                return False
        except Exception:
            logger.exception("ai_provider_ping_failed provider=%s", provider)
        return False
