import os

import pytest

from tpgk.ai_client import AIClient
from tpgk.notes import NotesManager
from tpgk.settings import Settings


def test_invalid_settings_are_replaced_with_defaults(monkeypatch, tmp_path):
    import tpgk.settings as settings_mod

    config_dir = tmp_path / "config"
    config_file = config_dir / "settings.json"
    config_dir.mkdir()
    config_file.write_text('{"font_size": "large", "terminal_rows": 9999}')
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(settings_mod, "CONFIG_FILE", str(config_file))
    Settings._instance = None
    Settings._loaded = False

    settings = Settings()
    assert settings.get("font_size") == 12
    assert settings.get("terminal_rows") == 24


def test_notes_cannot_escape_notes_directory(tmp_path):
    settings = Settings()
    settings.set("notes_dir", str(tmp_path))
    manager = NotesManager()

    with pytest.raises(ValueError):
        manager.write_note("secret", "../outside.md")
    with pytest.raises(ValueError):
        manager.write_note("secret", os.path.join(str(tmp_path), "outside.md"))


def test_notes_reject_symlink(tmp_path):
    settings = Settings()
    settings.set("notes_dir", str(tmp_path))
    target = tmp_path / "target.md"
    target.write_text("original")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    with pytest.raises(ValueError):
        NotesManager().open_notes("link.md")


def test_ai_rollback_removes_the_exact_message_object():
    client = AIClient("openai")
    first = {"role": "user", "content": "same"}
    second = {"role": "user", "content": "same"}
    client._messages = [first, second]

    client._remove_message(second)

    assert client._messages == [first]


def test_history_add_many_commits_all_rows(isolated_history):
    assert isolated_history.add_many(["one", "two"], "/tmp") == 2
    assert [row[0] for row in isolated_history.get_all(2)] == ["two", "one"]


def test_tpgk_command_matching_respects_word_boundaries():
    from tpgk.terminal import TerminalBox

    assert TerminalBox._is_tpgk_command(object(), "/history ssh")
    assert not TerminalBox._is_tpgk_command(object(), "/history_backup")
    assert not TerminalBox._is_tpgk_command(object(), "/clearance")


def test_ai_context_is_bounded_and_redacted():
    from tpgk.terminal import TerminalBox

    class ContextTerminal:
        def _get_visible_text(self, _lines):
            return "password=secret sk-12345678901234567890"

    prompt = TerminalBox._build_ai_context_prompt(ContextTerminal(), "/ai context 2 explain")
    assert "[REDACTED SECRET]" in prompt
    assert "[REDACTED TOKEN]" in prompt
    assert TerminalBox._build_ai_context_prompt(ContextTerminal(), "/ai context 201 explain") is None


def test_gemini_system_prompt_uses_system_instruction(monkeypatch):
    import tpgk.ai_client as ai_module

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    class Requests:
        def __init__(self):
            self.payload = None

        def post(self, *_args, **kwargs):
            self.payload = kwargs["json"]
            return Response()

    requests = Requests()
    monkeypatch.setattr(ai_module, "_requests", requests)
    client = AIClient("gemini", api_key="test")
    client.set_system_prompt("system")
    client.chat("hello")

    assert requests.payload["systemInstruction"]["parts"][0]["text"] == "system"
    assert all(item["role"] != "system" for item in requests.payload["contents"])
