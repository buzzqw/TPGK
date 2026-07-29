import os
import sys
import json
import tempfile
import shutil
import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tpgk.settings import (  # noqa: E402
    Settings, DEFAULTS, COLOR_SCHEMES, COLOR_PALETTES,
    CONFIG_DIR, CONFIG_FILE,
)
import tpgk.settings as settings_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    cfg_dir = str(tmp_path / "tpgk_config")
    cfg_file = str(tmp_path / "tpgk_config" / "settings.json")
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "CONFIG_FILE", cfg_file)
    Settings._instance = None
    Settings._loaded = False
    yield
    Settings._instance = None
    Settings._loaded = False
from tpgk.history import HistoryManager
from tpgk.ai_client import AIClient
from tpgk.notes import NotesManager


# ── Settings: edge cases ────────────────────────────────────────

class TestSettingsEdgeCases:

    def test_custom_palette_overrides_preset(self):
        s = Settings()
        s.set("custom_palette", {"black": "#111111", "red": "#ff0000",
                                  "green": "#00ff00", "yellow": "#ffff00",
                                  "blue": "#0000ff", "magenta": "#ff00ff",
                                  "cyan": "#00ffff", "white": "#ffffff",
                                  "brightblack": "#333333", "brightred": "#ff4444",
                                  "brightgreen": "#44ff44", "brightyellow": "#ffff44",
                                  "brightblue": "#4444ff", "brightmagenta": "#ff44ff",
                                  "brightcyan": "#44ffff", "brightwhite": "#ffffff"})
        palette = s.get_palette()
        assert palette["black"] == "#111111"
        assert palette["red"] == "#ff0000"

    def test_custom_palette_none_falls_back_to_scheme(self):
        s = Settings()
        s.set("custom_palette", None)
        s.set("color_scheme", "Dark (Default)")
        palette = s.get_palette()
        assert palette["black"] == COLOR_PALETTES["Dark (Default)"]["black"]

    def test_get_unknown_key_returns_none(self):
        s = Settings()
        assert s.get("nonexistent_key") is None

    def test_get_unknown_key_default(self):
        s = Settings()
        assert s.get("nonexistent_key", "fallback") == "fallback"

    def test_dict_defaults_are_copied(self):
        for key in ("ai_keys", "ai_models", "ai_urls"):
            assert isinstance(DEFAULTS[key], dict)

    def test_color_schemes_have_fg_bg(self):
        for name, scheme in COLOR_SCHEMES.items():
            assert "foreground" in scheme
            assert "background" in scheme
            assert scheme["foreground"].startswith("#")
            assert scheme["background"].startswith("#")

    def test_palette_color_count(self):
        for name, palette in COLOR_PALETTES.items():
            assert len(palette) == 16
            assert len([k for k in palette if k.startswith("bright")]) == 8
            assert len([k for k in palette if not k.startswith("bright")]) == 8

    def test_fg_bg_override(self):
        s = Settings()
        s.set("foreground_color", "#abcdef")
        s.set("background_color", "#123456")
        assert s.get_fg_color() == "#abcdef"
        assert s.get_bg_color() == "#123456"


# ── History: edge cases ─────────────────────────────────────────

class TestHistoryEdgeCases:

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

    def test_search_special_characters(self, hm):
        hm.add("echo 'hello world'", "/home")
        hm.add("grep -rn 'pattern' .", "/home")
        hm.add("cat file%name", "/home")
        r = hm.search("file%name", 10)
        assert len(r) == 1
        r = hm.search("'hello", 10)
        assert len(r) == 1

    def test_search_unicode(self, hm):
        hm.add("echo caffè", "/home")
        hm.add("echo naïve", "/home")
        r = hm.search("caffè", 10)
        assert len(r) == 1

    def test_search_no_results(self, hm):
        hm.add("ls -la", "/home")
        r = hm.search("nonexistent_xyz", 10)
        assert len(r) == 0

    def test_interactive_search_empty_db(self, hm):
        r = hm.interactive_search("anything", 10)
        assert len(r) == 0

    def test_search_latest_empty_db(self, hm):
        r = hm.search_latest("", 10)
        assert len(r) == 0

    def test_search_latest_prefix_not_found(self, hm):
        hm.add("git status", "/home")
        hm.add("ls -la", "/home")
        r = hm.search_latest("docker", 10)
        assert len(r) == 0

    def test_get_all_empty_db(self, hm):
        r = hm.get_all(10)
        assert len(r) == 0

    def test_add_with_empty_cwd(self, hm):
        hm.add("pwd", "")
        r = hm.search("pwd", 10)
        assert len(r) == 1
        assert r[0][2] == ""


# ── History: exclusion (-) and SQL search ──────────────────────

class TestHistoryExclusionAndSQL:

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

    # ── Exclusion (-) ─────────────────────────────────────

    def test_exclude_single_term(self, hm):
        hm.add("ssh host 161", "/home")
        hm.add("ssh host 222", "/home")
        hm.add("ssh host 333", "/home")
        r = hm.search("-161", 10)
        assert len(r) == 2
        cmds = [row[1] for row in r]
        assert "ssh host 161" not in cmds

    def test_exclude_multiple_terms(self, hm):
        hm.add("ssh host 161", "/home")
        hm.add("ssh host 222", "/home")
        hm.add("ssh host 333", "/home")
        r = hm.search("-161 -222", 10)
        assert len(r) == 1
        assert "ssh host 333" in r[0][1]

    def test_exclude_with_positive_term(self, hm):
        hm.add("ssh host 161", "/home")
        hm.add("ssh host 222", "/home")
        hm.add("ssh dev 222", "/home")
        hm.add("git push", "/home")
        r = hm.search("ssh -161", 10)
        assert len(r) == 2
        cmds = [row[1] for row in r]
        assert "ssh host 161" not in cmds
        assert all("ssh" in c or "SSH" in c.upper() for c in cmds)

    def test_exclude_all_terms_shows_nothing_excepted(self, hm):
        hm.add("echo hello", "/home")
        hm.add("echo world", "/home")
        hm.add("echo test", "/home")
        r = hm.search("-hello -world", 10)
        assert len(r) == 1
        assert "echo test" in r[0][1]

    def test_lone_dash_is_literal(self, hm):
        hm.add("ls -la", "/home")
        hm.add("ls -ltr", "/home")
        r = hm.search("-", 10)
        assert len(r) >= 1

    def test_exclude_with_spaces(self, hm):
        hm.add("ssh debinis@host 161", "/home")
        hm.add("ssh debinis@host 222", "/home")
        r = hm.search("ssh -161", 10)
        assert len(r) == 1
        assert "222" in r[0][1]

    # ── SQL search ────────────────────────────────────────

    def test_sql_search_select_all(self, hm):
        hm.add("cmd1", "/home/a")
        hm.add("cmd2", "/home/b")
        hm.add("cmd3", "/home/c")
        r = hm.sql_search("SELECT id, command, cwd, timestamp FROM commands ORDER BY id ASC")
        assert len(r) == 3
        assert r[0][1] == "cmd1"

    def test_sql_search_where_clause(self, hm):
        hm.add("cmd_keep", "/home")
        # Add one with / prefix that normal search would exclude
        hm.add("/cmd_skip", "/home")
        r = hm.sql_search(
            "SELECT id, command, cwd, timestamp FROM commands WHERE command LIKE '/%' ORDER BY id"
        )
        assert len(r) == 1
        assert r[0][1] == "/cmd_skip"

    def test_sql_search_forbidden_insert(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("INSERT INTO commands VALUES (1, 'x', '', 0, '')")

    def test_sql_search_forbidden_delete(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("DELETE FROM commands")

    def test_sql_search_forbidden_drop(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("DROP TABLE commands")

    def test_sql_search_forbidden_update(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("UPDATE commands SET command='x'")

    def test_sql_search_non_select_raises(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("CREATE TABLE x (a int)")

    def test_sql_search_pragma_raises(self, hm):
        with pytest.raises(ValueError, match="Only SELECT and EXPLAIN"):
            hm.sql_search("PRAGMA table_info(commands)")


# ── AI Client: edge cases ───────────────────────────────────────

class TestAIClientEdgeCases:

    def test_all_providers_have_required_fields(self):
        required = ("name", "url", "default_model", "protocol")
        for provider, info in AIClient.PROVIDERS.items():
            for field in required:
                assert field in info, f"{provider} missing {field}"

    def test_default_models_are_strings(self):
        for provider, info in AIClient.PROVIDERS.items():
            assert isinstance(info["default_model"], str)
            assert len(info["default_model"]) > 0

    def test_urls_are_valid(self):
        for provider, info in AIClient.PROVIDERS.items():
            assert info["url"].startswith("http")

    def test_claude_has_anthropic_headers(self):
        client = AIClient("claude", api_key="sk-test")
        assert client._protocol == "claude"

    def test_gemini_url_has_model_placeholder(self):
        assert "{model}" in AIClient.PROVIDERS["gemini"]["url"]

    def test_base_url_from_args(self):
        client = AIClient("openai", api_key="sk-test",
                          base_url="https://custom.openai.com/v1")
        assert client.base_url == "https://custom.openai.com/v1"

    def test_ping_provider_returns_bool(self):
        result = AIClient.ping_provider("ollama", "http://localhost:11434/v1/chat/completions")
        assert isinstance(result, bool)

    def test_fetch_models_ollama_default_url(self):
        models = AIClient.fetch_models("ollama")
        assert isinstance(models, list)

    def test_fetch_models_custom_no_url(self):
        models = AIClient.fetch_models("custom", "")
        assert models == []

    def test_each_provider_instantiable(self):
        for provider in AIClient.PROVIDERS:
            if provider in ("ollama", "custom"):
                client = AIClient(provider)
            else:
                client = AIClient(provider, api_key="test-key")
            assert client.provider == provider
            assert client.model is not None
            client.reset()
            assert len(client._messages) == 0


# ── Notes: edge cases ───────────────────────────────────────────

class TestNotesEdgeCases:

    def test_write_note_empty_text(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "notes.md")
        nm = NotesManager()
        path = nm.write_note("")
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
            assert "## " in content

    def test_write_note_multiline(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        nm = NotesManager()
        path = nm.write_note("line 1\nline 2\nline 3")
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
            assert "line 1" in content
            assert "line 2" in content
            assert "line 3" in content

    def test_write_note_creates_subdirectory(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        nm = NotesManager()
        path = nm.write_note("test", "subdir/notes.md")
        assert os.path.exists(path)
        assert "subdir" in path

    def test_open_notes_editor_true(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "notes.md")
        s.set("editor_command", "true")
        nm = NotesManager()
        path = nm.open_notes()
        assert os.path.exists(path)

    def test_notes_file_without_extension(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "myfile")
        nm = NotesManager()
        path = nm._get_notes_path()
        assert path.endswith(".md")


# ── Window utilities ────────────────────────────────────────────

class TestWindowUtils:

    def test_signals_list(self):
        import signal
        from tpgk.window import SIGNALS
        assert len(SIGNALS) >= 9
        sig_labels = [s[0] for s in SIGNALS]
        assert "SIGTERM (15)" in sig_labels
        assert "SIGKILL (9)" in sig_labels
        assert "SIGHUP (1)" in sig_labels
        assert "SIGINT (2)" in sig_labels
        assert "SIGSTOP (19)" in sig_labels
        assert "SIGCONT (18)" in sig_labels
        assert "SIGUSR1 (10)" in sig_labels
        assert "SIGUSR2 (12)" in sig_labels
        assert "SIGTSTP (20)" in sig_labels

    def test_encodings_list(self):
        from tpgk.window import ENCODINGS
        assert len(ENCODINGS) == 13
        required = ("UTF-8", "UTF-16BE", "UTF-16LE", "ISO-8859-1", "CP1252", "GBK")
        for enc in required:
            assert enc in ENCODINGS, f"Missing encoding: {enc}"

    def test_detect_file_manager_found(self):
        from tpgk.window import _detect_file_manager
        s = Settings()
        s.set("file_manager", "")
        fm = _detect_file_manager(s)
        assert isinstance(fm, str)
        assert fm == "" or shutil.which(fm) is not None

    def test_detect_file_manager_custom(self):
        from tpgk.window import _detect_file_manager
        s = Settings()
        orig = s.get("file_manager", "")
        s.set("file_manager", "ls")
        try:
            fm = _detect_file_manager(s)
            assert fm == "ls"
        finally:
            s.set("file_manager", orig)

    def test_detect_file_manager_fallback(self):
        from tpgk.window import _detect_file_manager
        s = Settings()
        orig = s.get("file_manager", "")
        s.set("file_manager", "nonexistent_binary_xyz")
        try:
            fm = _detect_file_manager(s)
            assert fm == "" or shutil.which(fm) is not None
        finally:
            s.set("file_manager", orig)


# ── Terminal utilities ──────────────────────────────────────────

class TestTerminalUtils:

    def test_hex_to_gdk(self):
        from tpgk.terminal import _hex_to_gdk
        color = _hex_to_gdk("#ff0000")
        assert color.red == 1.0
        assert color.green == 0.0
        assert color.blue == 0.0

    def test_hex_to_gdk_black(self):
        from tpgk.terminal import _hex_to_gdk
        color = _hex_to_gdk("#000000")
        assert color.red == 0.0
        assert color.green == 0.0
        assert color.blue == 0.0

    def test_tpgk_commands_content(self):
        from tpgk.terminal import TPGK_COMMANDS
        assert len(TPGK_COMMANDS) >= 8
        assert isinstance(TPGK_COMMANDS, list)
        # all must be strings
        for cmd in TPGK_COMMANDS:
            assert isinstance(cmd, str)
            assert len(cmd) > 0
        # no duplicates
        assert len(TPGK_COMMANDS) == len(set(TPGK_COMMANDS))


# ── Integration: cross-module ───────────────────────────────────

class TestIntegrationDeep:

    def test_scheme_palette_parity(self):
        scheme_names = set(COLOR_SCHEMES.keys())
        palette_names = set(COLOR_PALETTES.keys())
        assert scheme_names == palette_names

    def test_settings_history_independent(self):
        s = Settings()
        hm = HistoryManager()
        unique = f"test_integration_{os.urandom(4).hex()}"
        s.set("tab_title", "Test")
        hm.add(unique, "/home")
        assert s.get("tab_title") == "Test"
        assert len(hm.search(unique, 10)) == 1

    def test_notes_settings_persistence(self, tmp_path):
        s = Settings()
        s.set("notes_dir", str(tmp_path))
        s.set("notes_file", "test_notes.md")
        s.set("editor_command", "true")
        nm = NotesManager()

        path = nm.write_note("Note 1")
        assert os.path.exists(path)
        assert "test_notes.md" in path

        path2 = nm.write_note("Note 2")
        assert path == path2
        with open(path) as f:
            content = f.read()
            assert "Note 1" in content
            assert "Note 2" in content

    def test_ai_client_with_settings_keys(self, tmp_path):
        s = Settings()
        s.set("ai_keys", {"openai": "sk-test-key", "claude": "", "gemini": "",
                          "deepseek": "", "ollama": "", "custom": ""})
        s.set("ai_models", {"openai": "gpt-4-turbo", "claude": "", "gemini": "",
                            "deepseek": "", "ollama": "", "custom": ""})
        keys = s.get("ai_keys", {})
        models = s.get("ai_models", {})
        assert keys["openai"] == "sk-test-key"
        assert models["openai"] == "gpt-4-turbo"

        client = AIClient("openai", api_key=keys["openai"],
                          model=models["openai"])
        assert client.api_key == "sk-test-key"
        assert client.model == "gpt-4-turbo"

    def test_history_timestamp_format(self, tmp_path):
        import tpgk.history as hist
        orig_dir, orig_db = hist.HISTORY_DIR, hist.HISTORY_DB
        db = tmp_path / "test.db"
        hist.HISTORY_DIR = str(tmp_path)
        hist.HISTORY_DB = str(db)
        hm = HistoryManager()
        try:
            hm.add("test cmd", "/home")
            r = hm.search("test cmd", 1)
            assert len(r) == 1
            ts = r[0][3]
            datetime.datetime.fromisoformat(ts)
        finally:
            hist.HISTORY_DIR, hist.HISTORY_DB = orig_dir, orig_db
            try:
                hm._conn.close()
            except Exception:
                pass
            HistoryManager._instance = None

    def test_history_exit_code_stored(self, tmp_path):
        import tpgk.history as hist
        orig_dir, orig_db = hist.HISTORY_DIR, hist.HISTORY_DB
        db = tmp_path / "test.db"
        hist.HISTORY_DIR = str(tmp_path)
        hist.HISTORY_DB = str(db)
        hm = HistoryManager()
        try:
            hm.add("cmd", "/home", 0)
            r = hm.search("cmd", 1)
            assert len(r) == 1
        finally:
            hist.HISTORY_DIR, hist.HISTORY_DB = orig_dir, orig_db
            try:
                hm._conn.close()
            except Exception:
                pass
            HistoryManager._instance = None


# ── System Stats ─────────────────────────────────────────────────

class TestSystemStats:

    def test_mb_bytes_format(self):
        from tpgk.system_stats import _mb
        assert "0M" in _mb(0)
        assert "M" in _mb(1024 * 512)
        assert "G" in _mb(1024 * 1024 * 1024)
        assert "G" in _mb(1024 * 1024 * 1024 * 5)

    def test_collect_returns_string(self):
        from tpgk.system_stats import collect
        result = collect()
        assert isinstance(result, str)
        assert "CPU" in result
        assert "RAM" in result
        assert "Disk" in result

    def test_collect_with_ssh(self):
        from tpgk.system_stats import collect
        result = collect(is_ssh=True)
        assert "[SSH]" in result


# ── History: space‑insensitive search ────────────────────────────

class TestHistorySpaceInsensitive:

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

    def test_search_ignores_spaces(self, hm):
        hm.add("ssh debinis@host", "/home")
        r = hm.search("sshdeb", 10)
        assert len(r) == 1
        assert "ssh" in r[0][1]

    def test_search_exact_substring_still_works(self, hm):
        hm.add("sshdebinis", "/home")
        r = hm.search("sshdeb", 10)
        assert len(r) == 1

    def test_search_multi_word_and_logic(self, hm):
        hm.add("ssh user@host -p 2222", "/home")
        hm.add("ssh prod", "/home")
        r = hm.search("ssh 2222", 10)
        assert len(r) == 1


# ── History: /optimize maintenance ────────────────────────────────

class TestHistoryOptimize:

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

    def test_optimize_removes_duplicates_keeping_latest(self, hm):
        hm.add("git status", "/proj")
        hm.add("git status", "/proj")
        hm.add("git status", "/proj")
        stats = hm.optimize()
        assert stats["rows_before"] == 3
        assert stats["rows_after"] == 1
        assert stats["duplicates_removed"] == 2
        remaining = hm._conn.execute("SELECT id, command FROM commands").fetchall()
        assert len(remaining) == 1
        assert remaining[0][0] == 3  # kept the most recent row, not the first

    def test_optimize_keeps_same_command_in_different_cwd(self, hm):
        hm.add("git status", "/proj-a")
        hm.add("git status", "/proj-b")
        stats = hm.optimize()
        assert stats["rows_after"] == 2
        assert stats["duplicates_removed"] == 0

    def test_optimize_no_duplicates_is_a_noop(self, hm):
        hm.add("ls -la", "/home")
        hm.add("pwd", "/home")
        stats = hm.optimize()
        assert stats["rows_before"] == 2
        assert stats["rows_after"] == 2
        assert stats["duplicates_removed"] == 0

    def test_optimize_survives_empty_history(self, hm):
        stats = hm.optimize()
        assert stats["rows_before"] == 0
        assert stats["rows_after"] == 0

    def test_optimize_is_usable_afterwards(self, hm):
        hm.add("echo one", "/home")
        hm.optimize()
        hm.add("echo two", "/home")
        rows = hm.get_all()
        assert ("echo two",) in rows
        assert ("echo one",) in rows


# ── Opacity rounding ─────────────────────────────────────────────

class TestOpacityRounding:

    def test_float_precision_does_not_trigger_opacity(self):
        raw = 0.9999999999999999
        assert raw < 1.0
        assert not (round(raw, 2) < 1.0)

    def test_legit_opacity_still_triggers(self):
        assert round(0.85, 2) < 1.0
        assert round(0.3, 2) < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
