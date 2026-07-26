import os
import sys
import json
import tempfile
import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tpgk.settings import Settings, DEFAULTS, COLOR_SCHEMES, COLOR_PALETTES
from tpgk.history import HistoryManager
from tpgk.ai_client import AIClient
from tpgk.notes import NotesManager
import tpgk.settings as settings_mod


# ── Settings ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    """All Settings tests must write to a temp file, never the real config."""
    cfg_dir = str(tmp_path / "tpgk_config")
    cfg_file = str(tmp_path / "tpgk_config" / "settings.json")
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "CONFIG_FILE", cfg_file)
    Settings._instance = None
    Settings._loaded = False
    yield
    Settings._instance = None
    Settings._loaded = False


class TestSettings:

    def test_singleton(self):
        s1 = Settings()
        s2 = Settings()
        assert s1 is s2

    def test_defaults_complete(self):
        required = [
            "font_name", "font_size", "color_scheme",
            "foreground_color", "background_color", "cursor_color", "cursor_shape",
            "highlight_color", "highlight_bg_color",
            "scrollback_lines", "scrollbar_position", "opacity",
            "shell_command", "notes_file", "notes_dir", "editor_command",
            "ai_provider", "ai_models", "ai_urls", "ai_keys", "ai_last_provider",
            "enable_transparency", "confirm_close", "tab_title",
            "tab_title_color", "tab_active_title_color",
            "encoding", "auto_copy_selection", "file_manager",
            "backspace_binding", "delete_binding", "custom_palette",
            "show_unsafe_paste_dialog", "show_tabs", "show_menubar", "show_toolbar",
            "dynamic_title", "login_shell", "cursor_blink",
            "scroll_on_output", "scroll_on_keystroke", "allow_bold_text",
        ]
        for key in required:
            assert key in DEFAULTS, f"Missing default: {key}"

    def test_get_set(self):
        s = Settings()
        s.set("tab_title", "TestTerm")
        assert s.get("tab_title") == "TestTerm"
        assert s["tab_title"] == "TestTerm"
        s["tab_title"] = "Other"
        assert s.get("tab_title") == "Other"

    def test_color_schemes_count(self):
        assert len(COLOR_SCHEMES) >= 7
        assert "Dark (Default)" in COLOR_SCHEMES
        assert "Nord" in COLOR_SCHEMES

    def test_color_palettes_16_colors(self):
        for name, palette in COLOR_PALETTES.items():
            assert len(palette) == 16, f"{name} has {len(palette)} colors"

    def test_get_palette_returns_dict(self):
        s = Settings()
        p = s.get_palette()
        assert isinstance(p, dict)
        assert len(p) == 16

    def test_get_fg_bg_colors(self):
        s = Settings()
        assert s.get_fg_color().startswith("#")
        assert s.get_bg_color().startswith("#")

    def test_persist_new_settings(self):
        s = Settings()
        s.set("scrollbar_position", "left")
        s.set("cursor_shape", "ibeam")
        s.set("backspace_binding", "control-h")
        s.set("delete_binding", "ascii-del")
        s.set("tab_title_color", "#ff0000")
        s.set("tab_active_title_color", "#00ff00")
        assert s.get("scrollbar_position") == "left"
        assert s.get("cursor_shape") == "ibeam"

    def test_all_settings_roundtrip(self):
        """Every non-dict, non-nullable setting must survive a save/load roundtrip."""
        import tpgk.settings as mod
        orig_file = mod.CONFIG_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                test_file = os.path.join(td, "settings.json")
                mod.CONFIG_FILE = test_file
                mod.CONFIG_DIR = td

                s1 = Settings.__new__(Settings)
                s1._data = {}
                Settings._instance = s1
                s1._loaded = False
                s1._callbacks = []

                nullable = {"custom_palette", "notes_file", "notes_dir", "file_manager",
                             "ai_provider", "ai_last_provider", "osc133"}
                dict_keys = {"ai_models", "ai_urls", "ai_keys", "ai_system_prompts", "custom_palette"}
                test_values = {
                    "font_name": "TestFont",
                    "font_size": 18,
                    "color_scheme": "Solarized Dark",
                    "foreground_color": "#112233",
                    "background_color": "#445566",
                    "cursor_color": "#ff0000",
                    "cursor_shape": "underline",
                    "highlight_color": "#aabbcc",
                    "highlight_bg_color": "#112244",
                    "scrollback_lines": 5000,
                    "scrollbar_position": "left",
                    "opacity": 0.85,
                    "shell_command": "/bin/zsh",
                    "notes_file": "my_notes.md",
                    "notes_dir": "/tmp/notes",
                    "editor_command": "vim",
                    "ai_provider": "openai",
                    "ai_models": {"openai": "gpt-4o"},
                    "ai_urls": {"ollama": "http://localhost:9999/v1"},
                    "ai_keys": {"openai": "sk-test123"},
                    "ai_last_provider": "claude",
                    "ai_system_prompts": {"openai": "Be helpful."},
                    "enable_transparency": True,
                    "confirm_close": False,
                    "tab_title": "MyTerm",
                    "tab_title_color": "#ff7700",
                    "tab_active_title_color": "#00ff00",
                    "encoding": "UTF-8",
                    "auto_copy_selection": False,
                    "file_manager": "thunar",
                    "backspace_binding": "control-h",
                    "delete_binding": "ascii-del",
                    "show_unsafe_paste_dialog": False,
                    "show_tabs": False,
                    "show_menubar": False,
                    "show_toolbar": True,
                    "dynamic_title": "before",
                    "login_shell": False,
                    "cursor_blink": False,
                    "scroll_on_output": False,
                    "scroll_on_keystroke": False,
                    "allow_bold_text": False,
                    "terminal_columns": 132,
                    "terminal_rows": 43,
                }

                for key, val in test_values.items():
                    s1.set(key, val)

                Settings._instance = None
                Settings._loaded = False

                s2 = Settings()
                s2.load()

                for key, expected in test_values.items():
                    actual = s2.get(key)
                    if isinstance(expected, dict):
                        assert actual == expected, f"{key}: {actual!r} != {expected!r}"
                    elif isinstance(expected, float):
                        assert abs(actual - expected) < 0.001, f"{key}: {actual!r} != {expected!r}"
                    else:
                        assert actual == expected, f"{key}: {actual!r} != {expected!r}"

        finally:
            mod.CONFIG_FILE = orig_file
            mod.CONFIG_DIR = os.path.dirname(orig_file)
            Settings._instance = None
            Settings._loaded = False

    def test_all_palette_keys_hex(self):
        required_keys = [
            "black", "red", "green", "yellow",
            "blue", "magenta", "cyan", "white",
            "brightblack", "brightred", "brightgreen", "brightyellow",
            "brightblue", "brightmagenta", "brightcyan", "brightwhite",
        ]
        for name, palette in COLOR_PALETTES.items():
            for key in required_keys:
                assert key in palette, f"{name} missing {key}"
                assert palette[key].startswith("#"), f"{name}.{key} not hex"


# ── History ─────────────────────────────────────────────────────

class TestHistory:

    @pytest.fixture
    def hm(self, tmp_path):
        import tpgk.history as hist
        orig_dir, orig_db = hist.HISTORY_DIR, hist.HISTORY_DB
        db = tmp_path / "test.db"
        hist.HISTORY_DIR = str(tmp_path)
        hist.HISTORY_DB = str(db)
        hm = HistoryManager()
        yield hm
        hist.HISTORY_DIR, hist.HISTORY_DB = orig_dir, orig_db
        try:
            hm._conn.close()
        except Exception:
            pass
        HistoryManager._instance = None

    def test_add_and_search(self, hm):
        hm.add("git status", "/home/test")
        hm.add("git push origin main", "/home/test")
        hm.add("ls -la", "/home/test")
        results = hm.search("git", 10)
        assert len(results) == 2
        results = hm.search("ls", 10)
        assert len(results) == 1

    def test_search_and_logic(self, hm):
        hm.add("ssh user@host -p 2222", "/home")
        hm.add("ssh prod", "/home")
        hm.add("git push", "/home")
        r = hm.search("ssh 2222", 10)
        assert len(r) == 1
        assert "2222" in r[0][1]

    def test_search_empty_returns_all(self, hm):
        hm.add("echo hello", "/home")
        r = hm.search("", 10)
        assert len(r) >= 1

    def test_interactive_search_deduplicates(self, hm):
        hm.add("git status", "/home")
        hm.add("git status", "/home")
        hm.add("git push", "/home")
        r = hm.interactive_search("git", 10)
        cmds = [row[0] for row in r]
        assert len(cmds) == len(set(cmds))

    def test_search_latest(self, hm):
        hm.add("git status", "/home")
        hm.add("grep pattern", "/home")
        hm.add("ls -la", "/home")
        r = hm.search_latest("git", 10)
        assert len(r) >= 1
        assert all(row[0].startswith("git") for row in r)

    def test_search_latest_empty_prefix(self, hm):
        hm.add("cmd1", "/home")
        hm.add("cmd2", "/home")
        r = hm.search_latest("", 10)
        assert len(r) >= 2

    def test_get_all(self, hm):
        hm.add("cmd1", "/home")
        hm.add("cmd2", "/home")
        r = hm.get_all(10)
        assert len(r) >= 2

    def test_clear(self, hm):
        hm.add("test", "/home")
        hm.clear()
        assert len(hm.search("test", 10)) == 0

    def test_trim_does_not_crash(self, hm):
        for i in range(100):
            hm.add(f"cmd{i}", "/home")
        r = hm.get_all(200)
        assert len(r) == 100


# ── AI Client ───────────────────────────────────────────────────

class TestAIClient:

    def test_six_providers(self):
        assert len(AIClient.PROVIDERS) == 6
        for p in ("openai", "claude", "gemini", "deepseek", "ollama", "custom"):
            assert p in AIClient.PROVIDERS
            assert "name" in AIClient.PROVIDERS[p]
            assert "default_model" in AIClient.PROVIDERS[p]
            assert "protocol" in AIClient.PROVIDERS[p]

    def test_init_defaults(self):
        client = AIClient("openai", api_key="sk-test")
        assert client.provider == "openai"
        assert client.model is not None
        assert client._protocol == "openai"
        assert len(client._messages) == 0

    def test_init_custom_model(self):
        client = AIClient("openai", api_key="sk-test", model="gpt-4-turbo")
        assert client.model == "gpt-4-turbo"

    def test_init_invalid_provider(self):
        with pytest.raises(KeyError):
            AIClient("invalid")

    def test_reset_messages(self):
        client = AIClient("openai", api_key="sk-test")
        client._messages.append({"role": "user", "content": "test"})
        assert len(client._messages) == 1
        client.reset()
        assert len(client._messages) == 0

    def test_static_methods_exist(self):
        assert hasattr(AIClient, "fetch_models")
        assert hasattr(AIClient, "ping_provider")

    def test_fetch_models_returns_list(self):
        models = AIClient.fetch_models(
            "ollama", "", "http://localhost:11434/v1/chat/completions"
        )
        assert isinstance(models, list)

    def test_protocol_types_correct(self):
        assert AIClient.PROVIDERS["openai"]["protocol"] == "openai"
        assert AIClient.PROVIDERS["claude"]["protocol"] == "claude"
        assert AIClient.PROVIDERS["gemini"]["protocol"] == "gemini"
        assert AIClient.PROVIDERS["deepseek"]["protocol"] == "openai"
        assert AIClient.PROVIDERS["ollama"]["protocol"] == "ollama"
        assert AIClient.PROVIDERS["custom"]["protocol"] == "openai"

    def test_ollama_no_key(self):
        client = AIClient("ollama")
        assert client.api_key == ""

    def test_base_url_override(self):
        client = AIClient("custom", base_url="http://example.com/v1/chat/completions")
        assert client.base_url == "http://example.com/v1/chat/completions"


# ── Notes ────────────────────────────────────────────────────────

class TestNotes:

    def test_write_note(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "notes.md")
        s.set("editor_command", "true")
        nm = NotesManager()
        path = nm.write_note("Test note content")
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
            assert "Test note content" in content
            assert content.lstrip().startswith("## ")

    def test_write_note_custom_file(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        nm = NotesManager()
        path = nm.write_note("Custom file note", "custom.md")
        assert os.path.exists(path)
        assert path.endswith("custom.md")

    def test_open_notes_creates_file(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "notes.md")
        s.set("editor_command", "true")
        nm = NotesManager()
        path = nm.open_notes()
        assert os.path.exists(path)

    def test_open_notes_custom_file(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("editor_command", "true")
        nm = NotesManager()
        path = nm.open_notes("custom.md")
        assert os.path.exists(path)
        assert "custom.md" in path


# ── Integration ─────────────────────────────────────────────────

class TestIntegration:

    def test_no_none_defaults(self):
        nullable = {"custom_palette", "notes_file", "notes_dir", "file_manager",
                     "ai_provider", "ai_last_provider"}
        for key, val in DEFAULTS.items():
            if isinstance(val, dict) or key in nullable:
                continue
            assert val is not None, f"{key} default is None"

    def test_scheme_names_consistent(self):
        scheme_names = set(COLOR_SCHEMES.keys())
        palette_names = set(COLOR_PALETTES.keys())
        for name in scheme_names:
            assert name in palette_names, f"Scheme {name} missing from palettes"

    def test_tpgk_commands_list(self):
        from tpgk.terminal import TPGK_COMMANDS
        assert "history" in TPGK_COMMANDS
        assert "ai" in TPGK_COMMANDS
        assert "connect" in TPGK_COMMANDS
        assert "help" in TPGK_COMMANDS
        assert "clear" in TPGK_COMMANDS
        assert "cls" in TPGK_COMMANDS
        assert "wnotes" in TPGK_COMMANDS
        assert "onotes" in TPGK_COMMANDS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
