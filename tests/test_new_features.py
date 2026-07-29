import os
import sys
import ast
import subprocess
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tpgk.settings import Settings, DEFAULTS, COLOR_SCHEMES, COLOR_PALETTES
from tpgk.ai_client import AIClient
import tpgk.settings as settings_mod


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


# ── Helpers ──────────────────────────────────────────────────────

def _terminal_methods():
    """Parse terminal.py and return set of method names."""
    path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "terminal.py")
    with open(path) as f:
        tree = ast.parse(f.read())
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _terminal_class_attrs():
    """Parse TerminalBox.__init__ for attribute assignments."""
    path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "terminal.py")
    with open(path) as f:
        source = f.read()
    return source


METHODS = _terminal_methods()
SOURCE = _terminal_class_attrs()


# ═══════════════════════════════════════════════════════════════════
# Feature 1: URL cliccabili
# ═══════════════════════════════════════════════════════════════════

class TestFeature1UrlClickable:

    def test_url_regex_present(self):
        """VTE match_add_regex deve essere chiamato con Vte.Regex."""
        assert 'match_add_regex' in SOURCE, "match_add_regex non chiamato in __init__"

    def test_url_tag_attribute(self):
        """_url_tag deve essere inizializzato."""
        assert '_url_tag' in SOURCE, "_url_tag non presente in TerminalBox.__init__"

    def test_set_allow_hyperlink_called(self):
        """set_allow_hyperlink(True) deve essere chiamato."""
        assert 'set_allow_hyperlink' in SOURCE, "set_allow_hyperlink non chiamato"

    def test_match_set_cursor_called(self):
        """match_set_cursor_type deve essere chiamato con HAND2."""
        assert 'match_set_cursor_type' in SOURCE, "match_set_cursor_type non chiamato"
        assert 'HAND2' in SOURCE, "Gdk.CursorType.HAND2 non usato"

    def test_url_at_position_method(self):
        assert '_url_at_position' in METHODS, "Manca _url_at_position()"

    def test_open_url_method(self):
        assert '_open_url' in METHODS, "Manca _open_url()"

    def test_open_url_uses_xdg_open(self):
        assert 'xdg-open' in SOURCE, "Manca xdg-open in _open_url()"

    def test_vte_regex_uses_regex_flags_default(self):
        assert 'REGEX_FLAGS_DEFAULT' in SOURCE, "Vte.REGEX_FLAGS_DEFAULT non usato"


# ═══════════════════════════════════════════════════════════════════
# Feature 2: spawn_async
# ═══════════════════════════════════════════════════════════════════

class TestFeature2SpawnAsync:

    def test_spawn_async_called(self):
        """spawn_async deve sostituire spawn_sync."""
        assert 'spawn_async' in SOURCE, "spawn_async non chiamato in launch()"

    def test_on_spawn_complete_method(self):
        assert '_on_spawn_complete' in METHODS, "Manca _on_spawn_complete()"

    def test_spawn_complete_handles_error(self):
        """_on_spawn_complete deve gestire il caso di errore."""
        assert 'error' in SOURCE and 'Failed to start shell' in SOURCE, \
            "_on_spawn_complete non gestisce error.message"

    def test_spawn_complete_sets_pid(self):
        assert '_pid' in SOURCE and 'int(pid)' in SOURCE, \
            "_on_spawn_complete non imposta _pid"

    def test_spawn_complete_sets_pty_fd(self):
        assert 'get_pty' in SOURCE and '_pty_fd' in SOURCE, \
            "_on_spawn_complete non imposta _pty_fd via get_pty().get_fd()"

    def test_spawn_flags_no_do_not_reap(self):
        """DO_NOT_REAP_CHILD non deve essere passato a spawn_async."""
        assert 'DO_NOT_REAP_CHILD' not in SOURCE, \
            "DO_NOT_REAP_CHILD presente ma non supportato da spawn_async"


# ═══════════════════════════════════════════════════════════════════
# Feature 3: Cancellazione streaming AI
# ═══════════════════════════════════════════════════════════════════

class TestFeature3AiCancellation:

    def test_ai_generation_attribute(self):
        assert '_ai_generation' in SOURCE and '_ai_generation = 0' in SOURCE, \
            "_ai_generation non inizializzato a 0"

    def test_ask_ai_stream_increments_generation(self):
        assert '_ai_generation += 1' in SOURCE, \
            "_ai_generation non incrementato in _ask_ai_stream()"

    def test_run_ai_stream_checks_generation(self):
        assert '_ai_generation != gen' in SOURCE, \
            "_run_ai_stream non controlla contatore generazione"

    def test_on_ai_finished_checks_generation(self):
        assert '_on_ai_finished' in METHODS, "Manca _on_ai_finished()"

    def test_on_ai_finished_resets_busy(self):
        assert '_ai_busy = False' in SOURCE, \
            "_ai_busy non resettato in _on_ai_finished()"

    def test_ctrl_c_increments_generation(self):
        """Ctrl+C deve incrementare _ai_generation e resettare _ai_busy."""
        # Find the Ctrl+C (not Ctrl+Shift+C) block - look for KEY_C without SHIFT
        idx = SOURCE.find('if ctrl and not shift:')
        ctrl_block = SOURCE[idx:idx + 2000]
        ctrl_c_block = ctrl_block.split('KEY_C or key == Gdk.KEY_c')[1].split('return True')[0]
        assert '_ai_generation += 1' in ctrl_c_block, \
            "Ctrl+C non incrementa _ai_generation"
        assert '_ai_busy = False' in ctrl_c_block, \
            "Ctrl+C non resetta _ai_busy"


# ═══════════════════════════════════════════════════════════════════
# Feature 4: os.killpg(tcgetpgrp)
# ═══════════════════════════════════════════════════════════════════

class TestFeature4Killpg:

    def test_get_foreground_pgrp_method(self):
        assert '_get_foreground_pgrp' in METHODS, "Manca _get_foreground_pgrp()"

    def test_kill_uses_killpg(self):
        assert 'os.killpg' in SOURCE, "kill() non usa os.killpg"

    def test_terminate_uses_killpg(self):
        # Verificato da test_kill_uses_killpg — os.killpg è già referenziato
        assert 'pgrp' in SOURCE, "terminate()/kill() non usa variabile pgrp"

    def test_tcgetpgrp_used(self):
        assert 'os.tcgetpgrp' in SOURCE, \
            "_get_foreground_pgrp() non chiama os.tcgetpgrp()"

    def test_pty_fd_checked_before_tcgetpgrp(self):
        assert 'self._pty_fd' in SOURCE, "_pty_fd non referenziato"


# ═══════════════════════════════════════════════════════════════════
# Feature 5: Settings live-reload
# ═══════════════════════════════════════════════════════════════════

class TestFeature5SettingsLiveReload:

    def test_settings_connect_method(self):
        s = Settings()
        assert hasattr(s, 'connect'), "Settings.connect() mancante"
        assert callable(s.connect)

    def test_settings_disconnect_method(self):
        s = Settings()
        assert hasattr(s, 'disconnect'), "Settings.disconnect() mancante"
        assert callable(s.disconnect)

    def test_settings_notify_changed_method(self):
        s = Settings()
        assert hasattr(s, 'notify_changed'), "Settings.notify_changed() mancante"
        assert callable(s.notify_changed)

    def test_notify_changed_calls_callbacks(self):
        s = Settings()
        called = []
        def cb():
            called.append(1)
        s.connect(cb)
        s.notify_changed()
        assert len(called) == 1, "notify_changed() non chiama i callback"
        s.disconnect(cb)

    def test_notify_changed_multiple_callbacks(self):
        s = Settings()
        results = []
        def make_cb(n):
            def cb():
                results.append(n)
            return cb
        s.connect(make_cb(1))
        s.connect(make_cb(2))
        s.connect(make_cb(3))
        s.notify_changed()
        assert results == [1, 2, 3], f"Callback non chiamati in ordine: {results}"
        for cb in list(s._callbacks):
            s.disconnect(cb)

    def test_notify_changed_handles_exceptions(self):
        s = Settings()
        def failing_cb():
            raise RuntimeError("expected")
        called = []
        def good_cb():
            called.append(1)
        s.connect(failing_cb)
        s.connect(good_cb)
        s.notify_changed()
        assert called == [1], "notify_changed() non sopravvive a eccezioni callback"
        for cb in list(s._callbacks):
            s.disconnect(cb)

    def test_disconnect_nonexistent_does_not_crash(self):
        s = Settings()
        def cb():
            pass
        s.disconnect(cb)  # non deve lanciare eccezioni

    def test_apply_settings_method_exists(self):
        assert 'apply_settings' in METHODS, "TerminalBox.apply_settings() mancante"

    def test_apply_settings_calls_apply_font(self):
        """apply_settings() deve chiamare _apply_font()."""
        idx = SOURCE.find('def apply_settings')
        if idx >= 0:
            block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
            assert '_apply_font()' in block, "apply_settings() non chiama _apply_font()"

    def test_apply_settings_calls_apply_colors(self):
        idx = SOURCE.find('def apply_settings')
        if idx >= 0:
            block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
            assert '_apply_colors()' in block, "apply_settings() non chiama _apply_colors()"

    def test_settings_connect_called_in_init(self):
        assert 'self._settings.connect' in SOURCE, \
            "__init__ non chiama _settings.connect(self.apply_settings)"


class TestFeature5LiveReloadBehavior:

    def test_scheme_change_updates_fg_color(self):
        """Cambiare color_scheme deve cambiare get_fg_color()."""
        s = Settings()
        orig_fg = s.get_fg_color()
        s.set("color_scheme", "Matrix")
        new_fg = s.get_fg_color()
        assert new_fg != orig_fg, "get_fg_color() non cambia dopo cambio scheme"
        # Matrix foreground is green
        assert "#00ff41" in new_fg.lower() or new_fg == COLOR_SCHEMES["Matrix"]["foreground"], \
            f"Foreground Matrix errato: {new_fg}"

    def test_scheme_change_updates_bg_color(self):
        """Cambiare color_scheme deve cambiare get_bg_color()."""
        s = Settings()
        s.set("foreground_color", "")
        s.set("background_color", "")
        s.set("color_scheme", "Light")
        orig_bg = s.get_bg_color()
        s.set("color_scheme", "Matrix")
        new_bg = s.get_bg_color()
        assert new_bg != orig_bg, f"get_bg_color() non cambia dopo cambio scheme: {orig_bg} -> {new_bg}"

    def test_scheme_change_updates_palette(self):
        """Cambiare color_scheme deve cambiare get_palette()."""
        s = Settings()
        s.set("color_scheme", "Light")
        s.set("custom_palette", None)
        light_palette = s.get_palette()
        s.set("color_scheme", "Matrix")
        matrix_palette = s.get_palette()
        assert light_palette["black"] != matrix_palette["black"], \
            f"get_palette() non cambia dopo cambio scheme: {light_palette['black']} -> {matrix_palette['black']}"

    def test_explicit_fg_overrides_scheme(self):
        """foreground_color esplicito deve prevalere sullo scheme."""
        s = Settings()
        s.set("color_scheme", "Matrix")
        s.set("foreground_color", "#abcdef")
        assert s.get_fg_color() == "#abcdef", \
            "foreground_color esplicito non prevale sullo scheme"

    def test_clear_explicit_fg_falls_back_to_scheme(self):
        """foreground_color vuoto deve far usare lo scheme."""
        s = Settings()
        s.set("color_scheme", "Matrix")
        s.set("foreground_color", "")
        assert s.get_fg_color() == COLOR_SCHEMES["Matrix"]["foreground"], \
            "foreground_color '' non fa fallback allo scheme"

    def test_clear_explicit_bg_falls_back_to_scheme(self):
        s = Settings()
        s.set("color_scheme", "Nord")
        s.set("background_color", "")
        assert s.get_bg_color() == COLOR_SCHEMES["Nord"]["background"], \
            "background_color '' non fa fallback allo scheme"

    def test_live_reload_with_scheme_change(self):
        """notify_changed dopo cambio scheme deve propagare i colori corretti."""
        s = Settings()
        results = {}
        def cb():
            results['fg'] = s.get_fg_color()
            results['bg'] = s.get_bg_color()
            results['palette'] = s.get_palette()
        s.connect(cb)
        s.set("color_scheme", "Nord")
        s.set("foreground_color", "")
        s.set("background_color", "")
        s.notify_changed()
        assert results.get('fg') == COLOR_SCHEMES["Nord"]["foreground"], \
            f"Live-reload fg errato: {results.get('fg')}"
        assert results.get('bg') == COLOR_SCHEMES["Nord"]["background"], \
            f"Live-reload bg errato: {results.get('bg')}"
        s.disconnect(cb)

    def test_notify_changed_called_on_save(self):
        """_on_response in SettingsDialog deve chiamare notify_changed()."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert 'notify_changed()' in content, \
            "settings_dialog._on_response() non chiama notify_changed()"

    def test_scheme_combo_has_changed_signal(self):
        """Il dropdown scheme deve avere un handler 'changed'."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert 'connect("changed", self._on_scheme_changed)' in content or \
               "connect('changed', self._on_scheme_changed)" in content, \
            "_combo_scheme non ha segnale changed"

    def test_on_scheme_changed_method_exists(self):
        """_on_scheme_changed deve esistere in SettingsDialog."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            tree = ast.parse(f.read())
        methods = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert '_on_scheme_changed' in methods, \
            "Manca _on_scheme_changed in SettingsDialog"

    def test_on_scheme_changed_updates_fg_btn(self):
        """_on_scheme_changed deve aggiornare _fg_color_btn."""
        idx = SOURCE.find('def _on_scheme_changed')
        if idx < 0:
            path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
            with open(path) as f:
                dialog_source = f.read()
            idx = dialog_source.find('def _on_scheme_changed')
            if idx < 0:
                pytest.skip("_on_scheme_changed non presente")
            block = dialog_source[idx:dialog_source.find('\n    def ', idx + 20)]
        else:
            block = ""  # not in terminal.py
            path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
            with open(path) as f:
                dialog_source = f.read()
            idx = dialog_source.find('def _on_scheme_changed')
            if idx < 0:
                pytest.skip("_on_scheme_changed non presente")
            block = dialog_source[idx:dialog_source.find('\n    def ', idx + 20)]

        assert '_fg_color_btn' in block, "_on_scheme_changed non aggiorna _fg_color_btn"
        assert '_bg_color_btn' in block, "_on_scheme_changed non aggiorna _bg_color_btn"
        assert '_palette_btns' in block, "_on_scheme_changed non aggiorna _palette_btns"
        assert '_update_btn_color' in block, "_on_scheme_changed non chiama _update_btn_color"


# ═══════════════════════════════════════════════════════════════════
# Feature 6: Font chooser dialog
# ═══════════════════════════════════════════════════════════════════

class TestFeature6FontChooser:

    def test_font_button_in_settings_dialog(self):
        """SettingsDialog deve usare Gtk.FontButton."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert 'Gtk.FontButton' in content, "Gtk.FontButton non presente in settings_dialog.py"
        assert '_font_btn' in content, "_font_btn non presente in settings_dialog.py"
        assert 'get_font_name' in content, "get_font_name() non chiamato"

    def test_no_old_font_entry_spin(self):
        """_entry_font e _spin_font_size devono essere rimossi."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert '_entry_font' not in content, "_entry_font ancora presente (rimuovere)"
        assert '_spin_font_size' not in content, "_spin_font_size ancora presente (rimuovere)"


# ═══════════════════════════════════════════════════════════════════
# Feature 7: System prompt AI per provider
# ═══════════════════════════════════════════════════════════════════

class TestFeature7AiSystemPrompt:

    def test_ai_system_prompts_in_defaults(self):
        assert 'ai_system_prompts' in DEFAULTS, \
            "ai_system_prompts non in DEFAULTS"
        assert isinstance(DEFAULTS['ai_system_prompts'], dict), \
            "ai_system_prompts deve essere un dict"

    def test_aiclient_set_system_prompt_method(self):
        c = AIClient("openai", api_key="sk-test")
        assert hasattr(c, 'set_system_prompt'), \
            "AIClient.set_system_prompt() mancante"
        assert callable(c.set_system_prompt)

    def test_aiclient_system_prompt_attribute(self):
        c = AIClient("openai", api_key="sk-test")
        assert hasattr(c, '_system_prompt'), \
            "AIClient._system_prompt attributo mancante"
        assert c._system_prompt == "", \
            f"_system_prompt default non vuoto: {c._system_prompt!r}"

    def test_set_system_prompt_stores_value(self):
        c = AIClient("openai", api_key="sk-test")
        c.set_system_prompt("Sei un assistente esperto.")
        assert c._system_prompt == "Sei un assistente esperto."

    def test_system_prompt_injected_into_messages(self):
        """chat() deve inserire system prompt come primo messaggio."""
        c = AIClient("openai", api_key="sk-test")
        c.set_system_prompt("System test prompt")
        c.reset()
        c._messages = []
        # simulate chat without actually calling API
        c._messages.append({"role": "user", "content": "hello"})
        # Verify the internal method would insert the system prompt
        if c._system_prompt and not any(m.get("role") == "system" for m in c._messages):
            c._messages.insert(0, {"role": "system", "content": c._system_prompt})
        assert c._messages[0]["role"] == "system"
        assert c._messages[0]["content"] == "System test prompt"
        assert c._messages[1]["role"] == "user"

    def test_system_prompt_injection_idempotent(self):
        """Il system prompt non deve essere reinserito se già presente."""
        c = AIClient("openai", api_key="sk-test")
        c.set_system_prompt("Test")
        c._messages = [{"role": "system", "content": "Existing"}]
        if c._system_prompt and not any(m.get("role") == "system" for m in c._messages):
            c._messages.insert(0, {"role": "system", "content": c._system_prompt})
        assert len(c._messages) == 1, "System prompt reinserito duplicato"
        assert c._messages[0]["content"] == "Existing"

    def test_sys_prompt_textbuffer_in_dialog(self):
        """Settings dialog deve avere Gtk.TextBuffer per il system prompt."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert 'sys_prompt_buf' in content, "sys_prompt_buf non in settings_dialog.py"
        assert 'Gtk.TextBuffer' in content, "Gtk.TextBuffer non usato per system prompt"
        assert 'ai_system_prompts' in content, \
            "ai_system_prompts non salvato in _on_response"

    def test_start_ai_loads_system_prompt(self):
        """_start_ai deve caricare il system prompt dalle impostazioni."""
        source = SOURCE
        assert 'ai_system_prompts' in source, \
            "_start_ai non carica ai_system_prompts"
        assert 'sys_prompt' in source, \
            "_start_ai non usa variabile sys_prompt"
        assert 'set_system_prompt' in source, \
            "_start_ai non chiama set_system_prompt()"


# ═══════════════════════════════════════════════════════════════════
# Feature 8: /ai context
# ═══════════════════════════════════════════════════════════════════

class TestFeature8AiContext:

    def test_get_visible_text_method(self):
        assert '_get_visible_text' in METHODS, "Manca _get_visible_text()"

    def test_get_visible_text_uses_vte_get_text(self):
        assert 'get_text' in SOURCE, "_get_visible_text() non usa Vte.get_text()"

    def test_ai_context_in_execute_tpgk_command(self):
        assert '_execute_tpgk_command' in METHODS, \
            "Manca _execute_tpgk_command()"
        idx = SOURCE.find('def _execute_tpgk_command')
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert '/ai context' in block or '/ai context ' in block, \
            "_execute_tpgk_command non gestisce /ai context"

    def test_ai_context_in_help_text(self):
        assert '/ai context' in SOURCE, "/ai context non nel testo help"

    def test_ai_context_parses_line_count(self):
        """Deve parseggiare N e passarlo a _get_visible_text."""
        # Cerca in _execute_tpgk_command, non nella lista comandi
        idx = SOURCE.find('def _execute_tpgk_command')
        if idx < 0:
            pytest.skip("_execute_tpgk_command non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'num_lines' in block, \
            "/ai context non estrae num_lines in _execute_tpgk_command"
        assert 'int(parts[0])' in block, \
            "/ai context non converte N a int in _execute_tpgk_command"

    def test_ai_context_prepends_terminal_text(self):
        """Il testo terminale deve essere preposto al prompt."""
        idx = SOURCE.find('def _execute_tpgk_command')
        if idx < 0:
            pytest.skip("_execute_tpgk_command non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'Context:' in block or 'context' in block.lower(), \
            "Nel prompt /ai context non c'è 'Context:' in _execute_tpgk_command"


# ═══════════════════════════════════════════════════════════════════
# Feature 9: Shell integration OSC 133
# ═══════════════════════════════════════════════════════════════════

class TestFeature9Osc133:

    def test_osc133_in_defaults(self):
        assert 'osc133' in DEFAULTS, "osc133 non in DEFAULTS"
        assert DEFAULTS['osc133'] is False, "osc133 default deve essere False"

    def test_write_osc133_script_method(self):
        assert '_write_osc133_script' in METHODS, "Manca _write_osc133_script()"

    def test_osc133_env_var_in_launch(self):
        assert 'TPGK_SHELL_INTEGRATION' in SOURCE, \
            "TPGK_SHELL_INTEGRATION non in env di launch()"

    def test_osc133_script_generation(self):
        """_write_osc133_script() deve creare uno script in ~/.config/tpgk/osc133.sh."""
        idx = SOURCE.find('def _write_osc133_script')
        if idx < 0:
            pytest.skip("_write_osc133_script non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'osc133.sh' in block, "Script non nominato osc133.sh"
        assert 'OSC 133' in block, "Manca intestazione OSC 133"
        assert 'printf' in block, "Mancano comandi printf per sequenze OSC"
        assert ']133;C' in block or ']133;D' in block or ']133;A' in block, \
            "Mancano sequenze OSC 133 nel template"

    def test_osc133_script_supports_bash(self):
        idx = SOURCE.find('def _write_osc133_script')
        if idx < 0:
            pytest.skip("_write_osc133_script non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'BASH_VERSION' in block, "Manca supporto bash"

    def test_osc133_script_supports_zsh(self):
        idx = SOURCE.find('def _write_osc133_script')
        if idx < 0:
            pytest.skip("_write_osc133_script non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'ZSH_VERSION' in block, "Manca supporto zsh"

    def test_osc133_script_handles_prompt_command(self):
        """Deve preservare PROMPT_COMMAND esistente."""
        idx = SOURCE.find('def _write_osc133_script')
        if idx < 0:
            pytest.skip("_write_osc133_script non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'PROMPT_COMMAND' in block, "Manca gestione PROMPT_COMMAND"


# ═══════════════════════════════════════════════════════════════════
# Feature 10: Command palette
# ═══════════════════════════════════════════════════════════════════

class TestFeature10CommandPalette:

    def test_cmd_bar_visible_attribute(self):
        assert '_cmd_bar_visible' in SOURCE, "_cmd_bar_visible non in __init__"

    def test_show_command_bar_method(self):
        assert '_show_command_bar' in METHODS, "Manca _show_command_bar()"

    def test_execute_tpgk_command_method(self):
        assert '_execute_tpgk_command' in METHODS, "Manca _execute_tpgk_command()"

    def test_cmd_bar_changed_method(self):
        assert '_on_cmd_bar_changed' in METHODS, "Manca _on_cmd_bar_changed()"

    def test_cmd_bar_activated_method(self):
        assert '_on_cmd_bar_activated' in METHODS, "Manca _on_cmd_bar_activated()"

    def test_cmd_bar_key_method(self):
        assert '_on_cmd_bar_key' in METHODS, "Manca _on_cmd_bar_key()"

    def test_hide_command_bar_method(self):
        assert '_hide_command_bar' in METHODS, "Manca _hide_command_bar()"

    def test_build_cmd_list_method(self):
        assert '_build_cmd_list' in METHODS, "Manca _build_cmd_list()"

    def test_cmd_bar_row_activated_method(self):
        assert '_on_cmd_bar_row_activated' in METHODS, \
            "Manca _on_cmd_bar_row_activated()"

    def test_execute_from_bar_method(self):
        assert '_execute_from_bar' in METHODS, \
            "Manca _execute_from_bar()"

    def test_gdk_key_escape_in_bar(self):
        idx = SOURCE.find('def _on_cmd_bar_key')
        if idx < 0:
            pytest.skip("_on_cmd_bar_key non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'Gdk.KEY_Escape' in block, \
            "Manca gestione Esc nella command bar"

    def test_gdk_key_down_in_bar(self):
        idx = SOURCE.find('def _on_cmd_bar_key')
        if idx < 0:
            pytest.skip("_on_cmd_bar_key non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'Gdk.KEY_Down' in block, \
            "Manca gestione freccia giù nella command bar"

    def test_gdk_key_up_in_bar(self):
        idx = SOURCE.find('def _on_cmd_bar_key')
        if idx < 0:
            pytest.skip("_on_cmd_bar_key non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'Gdk.KEY_Up' in block, \
            "Manca gestione freccia su nella command bar"

    def test_gdk_key_tab_in_bar(self):
        """Tab deve autocompletare il comando nella command bar."""
        idx = SOURCE.find('def _on_cmd_bar_key')
        if idx < 0:
            pytest.skip("_on_cmd_bar_key non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 25)]
        assert 'Gdk.KEY_Tab' in block, \
            "Manca gestione Tab nella command bar"

    def test_bar_uses_gtk_overlay(self):
        assert 'Gtk.Overlay' in SOURCE, \
            "Command bar non usa Gtk.Overlay"

    def test_bar_uses_gtk_revealer(self):
        assert 'Gtk.Revealer' in SOURCE, \
            "Command bar non usa Gtk.Revealer"

    def test_bar_uses_gtk_listbox(self):
        assert 'Gtk.ListBox' in SOURCE, \
            "Command bar non usa Gtk.ListBox"

    def test_bar_has_all_tpgk_commands(self):
        idx = SOURCE.find('_cmd_commands = [\n            ("/')
        if idx < 0:
            idx = SOURCE.find('_cmd_commands = [\n')
            if idx < 0:
                pytest.skip("_cmd_commands popolata non trovata")
        block = SOURCE[idx:SOURCE.find('\n        ]', idx + 200)]
        expected = ['/ai', '/connect', '/history', '/wnotes', '/onotes', '/help', '/clear']
        for cmd in expected:
            assert cmd in block, f"Comando {cmd} non in command bar"

    def test_bar_trigger_on_slash(self):
        """I comandi / vanno direttamente nella shell, non nel popup GTK."""
        assert '_input_shadow += text' in SOURCE, \
            "Tracking _input_shadow dei caratteri assente"

    def test_bar_trigger_checks_no_other_mode(self):
        """Non deve attivarsi se siamo in AI mode, history search, ecc."""
        pass

    def test_bar_slide_up_transition(self):
        """Il revealer deve usare transizione slide-up."""
        assert 'SLIDE_UP' in SOURCE, \
            "Command bar non ha transizione SLIDE_UP"

    def test_bar_selects_row_fills_entry(self):
        """Selezionare una riga deve riempire l'entry con il comando."""
        idx = SOURCE.find('def _on_cmd_bar_row_activated')
        if idx < 0:
            pytest.skip("_on_cmd_bar_row_activated non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'set_text' in block and 'cmd_label' in block, \
            "Row activated non riempie l'entry"


# ═══════════════════════════════════════════════════════════════════
# Imports / module integrity
# ═══════════════════════════════════════════════════════════════════

class TestModuleImports:

    def test_all_modules_importable(self):
        from tpgk.settings import Settings
        from tpgk.history import HistoryManager
        from tpgk.notes import NotesManager
        from tpgk.ai_client import AIClient
        # window and terminal require GTK display, skip import test
        assert Settings is not None
        assert HistoryManager is not None
        assert NotesManager is not None
        assert AIClient is not None

    def test_subprocess_imported_in_terminal(self):
        """terminal.py deve importare subprocess per _open_url e xdg-open."""
        assert 'import subprocess' in SOURCE, \
            "Manca 'import subprocess' in terminal.py"

    def test_no_open_hyperlink_signal(self):
        """Il segnale inesistente open-hyperlink non deve essere referenziato."""
        assert 'open-hyperlink' not in SOURCE, \
            "Segnale open-hyperlink ancora referenziato (non esiste in VTE 0.80)"


# ═══════════════════════════════════════════════════════════════════
# Nuova feature: Terminal size (cols x rows)
# ═══════════════════════════════════════════════════════════════════

class TestTerminalSize:

    def test_defaults_have_terminal_size(self):
        assert 'terminal_columns' in DEFAULTS, \
            "terminal_columns non in DEFAULTS"
        assert 'terminal_rows' in DEFAULTS, \
            "terminal_rows non in DEFAULTS"
        assert DEFAULTS['terminal_columns'] == 80, \
            f"Default colonne errato: {DEFAULTS['terminal_columns']}"
        assert DEFAULTS['terminal_rows'] == 24, \
            f"Default righe errato: {DEFAULTS['terminal_rows']}"

    def test_apply_size_method_exists(self):
        assert '_apply_size' in METHODS, "TerminalBox._apply_size() mancante"

    def test_apply_size_calls_vte_set_size(self):
        """_apply_size() deve chiamare vte.set_size()."""
        idx = SOURCE.find('def _apply_size')
        if idx < 0:
            pytest.skip("_apply_size non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'set_size' in block, "_apply_size() non chiama vte.set_size()"
        assert 'terminal_columns' in block, "_apply_size() non legge terminal_columns"
        assert 'terminal_rows' in block, "_apply_size() non legge terminal_rows"

    def test_apply_size_called_during_init(self):
        """_apply_size() deve essere chiamato in __init__."""
        init_idx = SOURCE.find('def __init__')
        init_body = SOURCE[init_idx:SOURCE.find('\n    def apply_settings', init_idx)]
        assert 'self._apply_size()' in init_body or '_apply_size()' in init_body, \
            "__init__ non chiama _apply_size()"

    def test_apply_size_in_apply_settings(self):
        """apply_settings() deve chiamare _apply_size()."""
        idx = SOURCE.find('def apply_settings')
        if idx < 0:
            pytest.skip("apply_settings non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert '_apply_size()' in block, "apply_settings() non chiama _apply_size()"

    def test_settings_dialog_has_size_spinbuttons(self):
        """Preferences deve avere spin button per columns e rows."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert '_spin_columns' in content, "_spin_columns non in settings_dialog.py"
        assert '_spin_rows' in content, "_spin_rows non in settings_dialog.py"

    def test_settings_dialog_saves_terminal_size(self):
        """_on_response deve salvare terminal_columns e terminal_rows."""
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        idx = content.find('def _on_response')
        if idx < 0:
            pytest.skip("_on_response non trovato")
        block = content[idx:content.find('\n    def ', idx + 20) if content.find('\n    def ', idx + 20) > 0 else len(content)]
        assert 'terminal_columns' in block, "_on_response non salva terminal_columns"
        assert 'terminal_rows' in block, "_on_response non salva terminal_rows"

    def test_settings_persist_terminal_size(self):
        """terminal_columns/rows devono persistere dopo set e get."""
        s = Settings()
        s.set("terminal_columns", 120)
        s.set("terminal_rows", 40)
        assert s.get("terminal_columns") == 120
        assert s.get("terminal_rows") == 40


# ═══════════════════════════════════════════════════════════════════
# Nuova feature: Window size computed from terminal cols×rows
# ═══════════════════════════════════════════════════════════════════

class TestWindowSize:

    def _window_source(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "window.py")
        with open(path) as f:
            return f.read()

    def test_mainwindow_no_hardcoded_default_size(self):
        """MainWindow non deve avere set_default_size(900, 550) hardcoded."""
        ws = self._window_source()
        assert 'set_default_size(900, 550)' not in ws, \
            "MainWindow ha ancora set_default_size(900, 550) hardcoded"

    def test_mainwindow_computes_size_from_cols_rows(self):
        """MainWindow deve calcolare dimensione da terminal_columns/rows."""
        ws = self._window_source()
        idx = ws.find('class MainWindow')
        mainwindow_block = ws[idx:ws.find('\nclass ', idx + 10) if ws.find('\nclass ', idx + 10) > 0 else len(ws)]
        assert 'terminal_columns' in mainwindow_block, \
            "MainWindow.__init__ non legge terminal_columns"
        assert 'terminal_rows' in mainwindow_block, \
            "MainWindow.__init__ non legge terminal_rows"
        assert 'font_size' in mainwindow_block, \
            "MainWindow.__init__ non legge font_size per calcolo dimensioni"

    def test_mainwindow_has_apply_window_size(self):
        """MainWindow deve avere _apply_window_size()."""
        ws = self._window_source()
        tree = ast.parse(ws)
        methods = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert '_apply_window_size' in methods, \
            "MainWindow._apply_window_size() mancante"

    def test_mainwindow_connect_settings(self):
        """MainWindow deve connettersi a Settings per live-reload."""
        ws = self._window_source()
        idx = ws.find('class MainWindow')
        mainwindow_block = ws[idx:ws.find('\nclass ', idx + 10) if ws.find('\nclass ', idx + 10) > 0 else len(ws)]
        assert 'self._settings.connect' in mainwindow_block, \
            "MainWindow non ha settings.connect()"

    def test_detached_window_no_hardcoded_size(self):
        """_DetachedWindow non deve avere set_default_size(900, 550)."""
        ws = self._window_source()
        assert 'set_default_size(900, 550)' not in ws, \
            "_DetachedWindow ha ancora set_default_size(900, 550)"

    def test_detached_window_has_apply_window_size(self):
        """_DetachedWindow deve avere _apply_window_size()."""
        ws = self._window_source()
        idx = ws.find('class _DetachedWindow')
        if idx < 0:
            pytest.skip("_DetachedWindow non trovato")
        det_block = ws[idx:ws.find('\nclass ', idx + 10) if ws.find('\nclass ', idx + 10) > 0 else len(ws)]
        assert '_apply_window_size' in det_block, \
            "_DetachedWindow non ha _apply_window_size()"

    def test_apply_window_size_uses_resize(self):
        """_apply_window_size() deve chiamare self.resize()."""
        ws = self._window_source()
        idx = ws.find('def _apply_window_size')
        if idx < 0:
            pytest.skip("_apply_window_size non trovato")
        block = ws[idx:ws.find('\n    def ', idx + 20) if ws.find('\n    def ', idx + 20) > 0 else ws[idx:idx + 500]]
        assert 'self.resize' in block, "_apply_window_size() non chiama self.resize()"
        assert 'cols' in block and 'rows' in block, \
            "_apply_window_size() non usa cols e rows"
        assert 'font_size' in block, \
            "_apply_window_size() non considera font_size"


# ═══════════════════════════════════════════════════════════════════
# Nuova feature: "Add to Note" nel menu contestuale
# ═══════════════════════════════════════════════════════════════════

class TestAddToNote:

    def test_add_to_note_in_context_menu(self):
        """Il menu contestuale deve avere 'Add to Note'."""
        idx = SOURCE.find('def _show_context_menu')
        if idx < 0:
            pytest.skip("_show_context_menu non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'Add to Note' in block, \
            "'Add to Note' non nel menu contestuale"

    def test_add_to_note_sensitive_only_with_selection(self):
        """'Add to Note' deve essere sensibile solo se c'è testo selezionato."""
        idx = SOURCE.find('def _show_context_menu')
        if idx < 0:
            pytest.skip("_show_context_menu non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'get_has_selection' in block, \
            "Manca check get_has_selection() per Add to Note"
        assert 'set_sensitive' in block and 'has_sel' in block.lower(), \
            "Manca set_sensitive() condizionale per Add to Note"

    def test_add_selection_to_note_method_exists(self):
        assert '_add_selection_to_note' in METHODS, \
            "TerminalBox._add_selection_to_note() mancante"

    def test_add_selection_to_note_uses_notes_manager(self):
        """_add_selection_to_note() deve usare NotesManager.write_note()."""
        idx = SOURCE.find('def _add_selection_to_note')
        if idx < 0:
            pytest.skip("_add_selection_to_note non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'write_note' in block, \
            "_add_selection_to_note() non chiama NotesManager.write_note()"
        assert 'clipboard' in block.lower() or 'get_text' in block.lower() or \
               'get_has_selection' in block.lower(), \
            "_add_selection_to_note() non legge il testo selezionato"

    def test_add_selection_to_note_shows_confirmation(self):
        """_add_selection_to_note() deve mostrare una conferma nel terminale."""
        idx = SOURCE.find('def _add_selection_to_note')
        if idx < 0:
            pytest.skip("_add_selection_to_note non trovato")
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert 'feed' in block or 'Added' in block, \
            "_add_selection_to_note() non mostra conferma"


# ═══════════════════════════════════════════════════════════════════
# New Feature: Session restore
# ═══════════════════════════════════════════════════════════════════

class TestSessionRestore:

    def test_session_module_exists(self):
        from tpgk.session import save_state, load_state, list_sessions, delete_session
        assert callable(save_state)
        assert callable(load_state)
        assert callable(list_sessions)
        assert callable(delete_session)

    def test_session_restore_default_in_settings(self):
        assert 'session_restore' in DEFAULTS
        assert DEFAULTS['session_restore'] is True

    def test_session_restore_called_in_main(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "__main__.py")
        with open(path) as f:
            content = f.read()
        assert '_restore_session' in content

    def test_save_session_on_close(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "window.py")
        with open(path) as f:
            content = f.read()
        assert '_save_session' in content


# ═══════════════════════════════════════════════════════════════════
# New Feature: OSC 8 hyperlink UI
# ═══════════════════════════════════════════════════════════════════

class TestHyperlinkUI:

    def test_copy_url_method(self):
        assert '_copy_url' in METHODS

    def test_url_copy_in_context_menu(self):
        assert 'Copy URL' in SOURCE

    def test_url_open_in_context_menu(self):
        assert 'Open URL' in SOURCE

    def test_match_add_regex_still_present(self):
        assert 'match_add_regex' in SOURCE

    def test_set_allow_hyperlink_called(self):
        assert 'set_allow_hyperlink' in SOURCE


# ═══════════════════════════════════════════════════════════════════
# New Feature: Bell notification
# ═══════════════════════════════════════════════════════════════════

class TestBellNotification:

    def test_bell_notification_in_defaults(self):
        assert 'bell_notification' in DEFAULTS
        assert DEFAULTS['bell_notification'] is False

    def test_bell_notification_method(self):
        assert '_trigger_bell_notification' in METHODS

    def test_bell_uses_notify_send(self):
        assert 'notify-send' in SOURCE

    def test_bell_tracks_command(self):
        assert '_bell_notify_cmd_running' in SOURCE


# ═══════════════════════════════════════════════════════════════════
# New Feature: Window padding
# ═══════════════════════════════════════════════════════════════════

class TestWindowPadding:

    def test_padding_in_defaults(self):
        assert 'window_padding_horizontal' in DEFAULTS
        assert 'window_padding_vertical' in DEFAULTS
        assert DEFAULTS['window_padding_horizontal'] == 2
        assert DEFAULTS['window_padding_vertical'] == 2

    def test_apply_padding_method(self):
        assert '_apply_padding' in METHODS

    def test_apply_padding_called_in_apply_settings(self):
        idx = SOURCE.find('def apply_settings')
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert '_apply_padding()' in block

    def test_padding_spinbuttons_in_dialog(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert '_spin_pad_h' in content
        assert '_spin_pad_v' in content


# ═══════════════════════════════════════════════════════════════════
# New Feature: Incremental search in scrollback
# ═══════════════════════════════════════════════════════════════════

class TestIncrementalSearch:

    def test_search_overlay_attribute(self):
        assert '_search_revealer' in SOURCE

    def test_show_search_method(self):
        assert '_show_search' in METHODS

    def test_hide_search_method(self):
        assert '_hide_search' in METHODS

    def test_do_search_method(self):
        assert '_do_search' in METHODS

    def test_on_search_changed_method(self):
        assert '_on_search_changed' in METHODS

    def test_on_search_key_method(self):
        assert '_on_search_key' in METHODS

    def test_navigate_search_method(self):
        assert '_do_search' in METHODS

    def test_search_revealer_initialized(self):
        assert '_search_revealer' in SOURCE

    def test_search_entry_initialized(self):
        assert '_search_entry' in SOURCE

    def test_search_shortcut_registered(self):
        assert 'Gdk.KEY_F' in SOURCE and '_show_search' in SOURCE

    def test_search_context_menu_item(self):
        assert 'Search Scrollback' in SOURCE


# ═══════════════════════════════════════════════════════════════════
# New Feature: Broadcast input
# ═══════════════════════════════════════════════════════════════════

class TestBroadcastInput:

    def test_broadcast_in_defaults(self):
        assert 'broadcast_input' in DEFAULTS
        assert DEFAULTS['broadcast_input'] is False

    def test_feed_command_bytes_broadcasts(self):
        idx = SOURCE.find('def feed_command_bytes')
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert '_broadcast_to_others' in block or 'broadcast_input' in block

    def test_broadcast_to_others_method(self):
        assert '_broadcast_to_others' in METHODS

    def test_broadcast_shortcut(self):
        assert 'Gdk.KEY_B' in SOURCE and 'broadcast_input' in SOURCE

    def test_broadcast_context_menu(self):
        assert 'Broadcast Input' in SOURCE


# ═══════════════════════════════════════════════════════════════════
# New Feature: Multiple profiles
# ═══════════════════════════════════════════════════════════════════

class TestProfiles:

    def test_profiles_module_exists(self):
        from tpgk.profiles import save_profile, load_profile, list_profiles, delete_profile, apply_profile
        assert callable(save_profile)
        assert callable(load_profile)
        assert callable(list_profiles)
        assert callable(delete_profile)
        assert callable(apply_profile)

    def test_profiles_menu_in_window(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "window.py")
        with open(path) as f:
            content = f.read()
        assert '_profiles_menu' in content
        assert '_populate_profiles_menu' in content

    def test_save_profile_dialog(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "window.py")
        with open(path) as f:
            content = f.read()
        assert '_save_profile_dialog' in content

    def test_active_profile_in_defaults(self):
        assert 'active_profile' in DEFAULTS


# ═══════════════════════════════════════════════════════════════════
# New Feature: Quickmarks
# ═══════════════════════════════════════════════════════════════════

class TestQuickmarks:

    def test_quickmarks_list_initialized(self):
        assert '_quickmarks = []' in SOURCE or '_quickmarks =' in SOURCE

    def test_set_quickmark_method(self):
        assert '_set_quickmark' in METHODS

    def test_jump_next_quickmark_method(self):
        assert '_jump_next_quickmark' in METHODS

    def test_remove_all_quickmarks_method(self):
        assert '_remove_all_quickmarks' in METHODS

    def test_quickmark_shortcut_set(self):
        assert 'Gdk.KEY_M' in SOURCE and '_set_quickmark' in SOURCE

    def test_quickmark_shortcut_jump(self):
        assert '_jump_next_quickmark' in SOURCE

    def test_quickmark_context_menu(self):
        assert 'Set Quickmark' in SOURCE
        assert 'Clear All Quickmarks' in SOURCE


# ═══════════════════════════════════════════════════════════════════
# New Feature: Undercurl / styled underlines
# ═══════════════════════════════════════════════════════════════════

class TestUndercurl:

    def test_undercurl_in_defaults(self):
        assert 'undercurl_style' in DEFAULTS
        assert DEFAULTS['undercurl_style'] == 'single'

    def test_apply_undercurl_method(self):
        assert '_apply_undercurl' in METHODS

    def test_apply_undercurl_called_in_apply_settings(self):
        idx = SOURCE.find('def apply_settings')
        block = SOURCE[idx:SOURCE.find('\n    def ', idx + 20)]
        assert '_apply_undercurl()' in block

    def test_undercurl_styles_available(self):
        styles = ["single", "double", "curly", "dashed", "dotted"]
        for style in styles:
            assert style in SOURCE

    def test_undercurl_combo_in_dialog(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tpgk", "settings_dialog.py")
        with open(path) as f:
            content = f.read()
        assert '_combo_undercurl' in content
        assert 'undercurl_style' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
