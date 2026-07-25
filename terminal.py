import os
import gi
import threading
import subprocess

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("Pango", "1.0")

from gi.repository import Gtk, Gdk, GLib, Pango, Vte
from tpgk.settings import Settings
from tpgk.history import HistoryManager
from tpgk.notes import NotesManager
from tpgk.ai_client import AIClient


TPGK_COMMANDS = ["history", "ai", "connect", "wnotes", "onotes", "help", "clear", "cls"]

_TPGK_PREFIXES = ("/ai", "/history", "/wnotes", "/onotes", "/connect", "/help", "/clear", "/cls")


class TerminalBox(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._window = window
        self._settings = Settings()
        self._history = HistoryManager()
        self._notes = NotesManager()

        self._vte = Vte.Terminal()
        self._vte.set_scrollback_lines(self._settings.get("scrollback_lines", 10000))
        self._vte.set_mouse_autohide(True)
        self._vte.set_scroll_on_output(self._settings.get("scroll_on_output", True))
        self._vte.set_scroll_on_keystroke(self._settings.get("scroll_on_keystroke", True))

        self._apply_font()
        self._apply_colors()

        if self._settings.get("cursor_blink", True):
            self._vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        else:
            self._vte.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)

        self._apply_cursor_shape()
        self._apply_palette()

        self._vte.set_audible_bell(False)
        self._vte.set_allow_bold(self._settings.get("allow_bold_text", True))

        self._apply_size()

        self._encoding = self._settings.get("encoding", "UTF-8")
        if self._encoding.upper() != "UTF-8":
            try:
                self._vte.set_encoding(self._encoding)
            except Exception:
                pass

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self._vte)
        self._scroll = scroll

        self._overlay = Gtk.Overlay()
        self._overlay.add(scroll)
        self.pack_start(self._overlay, True, True, 0)

        self._apply_scrollbar_position()

        self._cmd_bar_revealer = Gtk.Revealer()
        self._cmd_bar_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self._cmd_bar_revealer.set_transition_duration(150)
        self._cmd_bar_revealer.set_halign(Gtk.Align.FILL)
        self._cmd_bar_revealer.set_valign(Gtk.Align.END)
        self._cmd_bar_revealer.set_reveal_child(False)
        self._overlay.add_overlay(self._cmd_bar_revealer)

        self._cmd_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._cmd_bar.set_size_request(-1, -1)
        self._cmd_bar_revealer.add(self._cmd_bar)

        outer_frame = Gtk.Frame()
        outer_frame.set_shadow_type(Gtk.ShadowType.ETCHED_OUT)
        outer_frame.get_style_context().add_class("command-bar-frame")
        self._cmd_bar.pack_start(outer_frame, True, True, 0)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer_frame.add(inner)

        self._cmd_entry = Gtk.Entry()
        self._cmd_entry.set_has_frame(False)
        self._cmd_entry.set_placeholder_text("/command [args]…")
        self._cmd_entry.connect("changed", self._on_cmd_bar_changed)
        self._cmd_entry.connect("activate", self._on_cmd_bar_activated)
        self._cmd_entry.connect("key-press-event", self._on_cmd_bar_key)
        inner.pack_start(self._cmd_entry, False, False, 0)

        self._cmd_list = Gtk.ListBox()
        self._cmd_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._cmd_list.connect("row-activated", self._on_cmd_bar_row_activated)
        cmd_scroll = Gtk.ScrolledWindow()
        cmd_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        cmd_scroll.set_max_content_height(200)
        cmd_scroll.add(self._cmd_list)
        inner.pack_start(cmd_scroll, True, True, 0)

        self._vte.connect("child-exited", self._on_child_exited)
        self._vte.connect("selection-changed", self._on_selection_changed)
        self._vte.connect("button-press-event", self._on_button_press)
        self._vte.connect("key-press-event", self._on_key_press)
        self._vte.connect("window-title-changed", self._on_title_changed)
        self._vte.connect("contents-changed", self._on_contents_changed)
        self._vte.add_events(Gdk.EventMask.SCROLL_MASK)

        url_regex = Vte.Regex.new_for_match(
            r'(https?://|ssh://|ftp://|git@|www\.)[\w\.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
            -1, Vte.REGEX_FLAGS_DEFAULT | 0x400)
        self._url_tag = self._vte.match_add_regex(url_regex, 0)
        self._vte.match_set_cursor_type(self._url_tag, Gdk.CursorType.HAND2)
        self._vte.set_allow_hyperlink(True)

        self._input_shadow = ""
        self._ai_mode = False
        self._ai_client = None
        self._ai_input = ""
        self._ai_busy = False
        self._ai_generation = 0
        self._history_search_mode = False
        self._history_search_query = ""
        self._history_search_index = 0
        self._history_search_results = []
        self._history_list_display = False
        self._history_list_results = []
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._connect_provider = None
        self._connect_model = None
        self._connect_key = ""
        self._connect_url = ""
        self._provider_list = []
        self._model_list = []
        self._history_show_results = []
        self._async_pending = False
        self._provider_worker = None
        self._model_worker = None

        self._comando_corrente = ""
        self._pid = -1
        self._pty_fd = -1

        self._settings.connect(self.apply_settings)

        self._cmd_bar_visible = False
        self._cmd_commands = [
            ("/ai", "Enter AI chat mode"),
            ("/ai context N <question>", "Include last N terminal lines as context"),
            ("/ai off", "Exit AI chat mode"),
            ("/connect [provider]", "Connect to AI provider"),
            ("/history [terms]", "Search command history"),
            ("/wnotes [-file.md] <text>", "Save timestamped note"),
            ("/onotes [-file.md]", "Open notes in editor"),
            ("/help", "Show all commands and shortcuts"),
            ("/clear", "Clear the terminal screen"),
            ("/cls", "Clear the terminal screen"),
        ]

        self.show_all()

    def _apply_font(self):
        family = self._settings.get("font_name", "Monospace")
        size = self._settings.get("font_size", 12)
        fd = Pango.FontDescription(f"{family} {size}")
        self._vte.set_font(fd)

    def _apply_colors(self):
        fg = _hex_to_gdk(self._settings.get_fg_color())
        bg = _hex_to_gdk(self._settings.get_bg_color())
        self._vte.set_colors(fg, bg, [])
        try:
            cursor_rgba = Gdk.RGBA()
            cursor_rgba.parse(self._settings.get("cursor_color", "#ffffff"))
            self._vte.set_color_cursor(cursor_rgba)
        except Exception:
            pass

    def _apply_cursor_shape(self):
        shape = self._settings.get("cursor_shape", "block")
        if shape == "underline":
            self._vte.set_cursor_shape(Vte.CursorShape.UNDERLINE)
        elif shape == "ibeam":
            self._vte.set_cursor_shape(Vte.CursorShape.IBEAM)
        else:
            self._vte.set_cursor_shape(Vte.CursorShape.BLOCK)

    def _apply_palette(self):
        # Fix #3: pass fg/bg to set_colors so the previous _apply_colors() is not overwritten
        fg = _hex_to_gdk(self._settings.get_fg_color())
        bg = _hex_to_gdk(self._settings.get_bg_color())
        palette = self._settings.get_palette()
        colors = []
        for key in ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
                     "brightblack", "brightred", "brightgreen", "brightyellow",
                     "brightblue", "brightmagenta", "brightcyan", "brightwhite"):
            hex_color = palette.get(key, "#000000")
            try:
                rgba = Gdk.RGBA()
                rgba.parse(hex_color)
                colors.append(rgba)
            except Exception:
                rgba = Gdk.RGBA()
                rgba.parse("#000000")
                colors.append(rgba)
        if colors:
            self._vte.set_colors(fg, bg, colors)
        # Apply highlight/selection colors (were set in settings but never applied)
        try:
            hl_fg = Gdk.RGBA()
            hl_fg.parse(self._settings.get("highlight_color", "#ffffff"))
            self._vte.set_color_highlight_foreground(hl_fg)
            hl_bg = Gdk.RGBA()
            hl_bg.parse(self._settings.get("highlight_bg_color", "#446688"))
            self._vte.set_color_highlight(hl_bg)
        except Exception:
            pass

    def _apply_scrollbar_position(self):
        # Fix #10 (scrollbar left): use set_placement instead of set_halign which does nothing
        pos = self._settings.get("scrollbar_position", "right")
        if pos == "left":
            self._scroll.set_placement(Gtk.CornerType.TOP_RIGHT)
        elif pos == "disabled":
            vscrollbar = self._scroll.get_vscrollbar()
            if vscrollbar:
                vscrollbar.hide()
        else:
            self._scroll.set_placement(Gtk.CornerType.TOP_LEFT)

    def _apply_size(self):
        cols = self._settings.get("terminal_columns", 80)
        rows = self._settings.get("terminal_rows", 24)
        self._vte.set_size(cols, rows)

    def apply_settings(self):
        self._apply_font()
        self._apply_colors()
        self._apply_cursor_shape()
        self._apply_palette()
        self._apply_scrollbar_position()
        self._apply_size()
        self._vte.set_scrollback_lines(self._settings.get("scrollback_lines", 10000))
        self._vte.set_scroll_on_output(self._settings.get("scroll_on_output", True))
        self._vte.set_scroll_on_keystroke(self._settings.get("scroll_on_keystroke", True))
        if self._settings.get("cursor_blink", True):
            self._vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        else:
            self._vte.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
        self._vte.set_allow_bold(self._settings.get("allow_bold_text", True))
        encoding = self._settings.get("encoding", "UTF-8")
        if encoding.upper() != "UTF-8":
            try:
                self._vte.set_encoding(encoding)
            except Exception:
                pass

    def update_font(self):
        self._apply_font()

    def update_colors(self):
        self._apply_colors()
        self._apply_cursor_shape()
        self._apply_palette()

    def set_scrollbar_visible(self, visible: bool):
        vscrollbar = self._scroll.get_vscrollbar()
        if vscrollbar:
            vscrollbar.set_visible(visible)

    def launch(self, cwd=None):
        shell = self._settings.get("shell_command", "/bin/bash")
        if self._settings.get("login_shell", True):
            argv = [shell, "-l"]
        else:
            argv = [shell]

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        if self._settings.get("osc133", False):
            env["TPGK_SHELL_INTEGRATION"] = "1"
            self._write_osc133_script()

        if cwd:
            wd = cwd
        else:
            wd = os.path.expanduser("~")

        self._vte.spawn_async(
            Vte.PtyFlags.DEFAULT,
            wd,
            argv,
            [f"{k}={v}" for k, v in env.items()],
            GLib.SpawnFlags.SEARCH_PATH,
            None, None, -1,
            None,
            self._on_spawn_complete,
            None,
        )

    def _write_osc133_script(self):
        script_dir = os.path.join(os.path.expanduser("~"), ".config", "tpgk")
        script_path = os.path.join(script_dir, "osc133.sh")
        script = r'''# TPGK OSC 133 Shell Integration
# Source this in your ~/.bashrc to enable shell integration:
#   [ -f ~/.config/tpgk/osc133.sh ] && source ~/.config/tpgk/osc133.sh

__tpgk_osc133_preexec() {
    printf '\033]133;C\007'
}
__tpgk_osc133_precmd() {
    local _exit=$?
    printf '\033]133;D;%s\007' "$_exit"
    printf '\033]133;A\007'
    printf '\033]7;%s\007' "file://$PWD"
}

if [ -n "$BASH_VERSION" ]; then
    trap '__tpgk_osc133_preexec' DEBUG
    if [ "${BASH_VERSINFO[0]}" -ge 4 ]; then
        PROMPT_COMMAND="__tpgk_osc133_precmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
    else
        PROMPT_COMMAND="__tpgk_osc133_precmd;${PROMPT_COMMAND}"
    fi
    printf '\033]133;A\007'
    printf '\033]7;%s\007' "file://$PWD"
elif [ -n "$ZSH_VERSION" ]; then
    autoload -Uz add-zsh-hook
    __tpgk_zsh_preexec() { printf '\033]133;C\007'; }
    __tpgk_zsh_precmd() { 
        printf '\033]133;D;%s\007' "$?"
        printf '\033]133;A\007'
        printf '\033]7;%s\007' "file://$PWD"
    }
    add-zsh-hook preexec __tpgk_zsh_preexec
    add-zsh-hook precmd __tpgk_zsh_precmd
    printf '\033]133;A\007'
    printf '\033]7;%s\007' "file://$PWD"
fi
'''
        os.makedirs(script_dir, exist_ok=True)
        try:
            with open(script_path, "w") as f:
                f.write(script)
        except OSError:
            pass

    def _on_spawn_complete(self, terminal, pid, error, user_data=None):
        if error:
            self._vte.feed(
                f"\r\n\x1b[31m[Failed to start shell: {error.message}]\x1b[0m\r\n".encode()
            )
        else:
            self._pid = int(pid)
            try:
                self._pty_fd = terminal.get_pty().get_fd()
            except Exception:
                self._pty_fd = -1

    def terminate(self):
        if self._pid > 0:
            try:
                pgrp = self._get_foreground_pgrp()
                if pgrp > 0:
                    os.killpg(pgrp, 15)
                else:
                    os.kill(self._pid, 15)
            except OSError:
                pass

    def kill(self, sig=15):
        if self._pid > 0:
            try:
                pgrp = self._get_foreground_pgrp()
                if pgrp > 0:
                    os.killpg(pgrp, int(sig))
                else:
                    os.kill(self._pid, int(sig))
            except OSError:
                pass

    def _get_foreground_pgrp(self):
        if self._pty_fd >= 0:
            try:
                return os.tcgetpgrp(self._pty_fd)
            except OSError:
                pass
        return -1

    def set_encoding(self, encoding: str):
        self._encoding = encoding
        try:
            self._vte.set_encoding(encoding)
        except Exception:
            pass

    def copy(self):
        self._vte.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self):
        # Fix #8: warn before pasting multi-line content
        if self._settings.get("show_unsafe_paste_dialog", True):
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            text = clipboard.wait_for_text()
            if text and ("\n" in text or "\r" in text):
                parent = self.get_toplevel()
                dialog = Gtk.MessageDialog(
                    parent if isinstance(parent, Gtk.Window) else None,
                    Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.WARNING,
                    Gtk.ButtonsType.YES_NO,
                    "The clipboard contains multiple lines.\n"
                    "Pasting could run commands unintentionally.\n\nPaste anyway?"
                )
                response = dialog.run()
                dialog.destroy()
                if response != Gtk.ResponseType.YES:
                    return
        self._vte.paste_clipboard()

    def paste_selection(self):
        self._vte.paste_primary()

    def select_all(self):
        self._vte.select_all()

    def reset(self, clear=False):
        self._vte.reset(True, clear)

    def set_read_only(self, ro: bool):
        self._vte.set_input_enabled(not ro)

    def get_cwd(self):
        if self._pid > 0:
            try:
                return os.readlink(f"/proc/{self._pid}/cwd")
            except OSError:
                pass
        return os.path.expanduser("~")

    # Fix #5: zoom is per-terminal and volatile (does not persist to settings)
    def zoom_in(self):
        self._vte.set_font_scale(self._vte.get_font_scale() * 1.1)

    def zoom_out(self):
        self._vte.set_font_scale(max(0.25, self._vte.get_font_scale() / 1.1))

    def zoom_reset(self):
        self._vte.set_font_scale(1.0)

    def feed_command(self, text: str):
        self._vte.feed_child(text.encode("utf-8"))

    def feed_command_bytes(self, data: bytes):
        self._vte.feed_child(data)

    def feed_display(self, text: str):
        """Write display-only text to the terminal screen (never to the shell stdin)."""
        self._vte.feed(text.replace("\n", "\r\n").encode("utf-8"))

    def _scroll_to_bottom(self):
        if self._settings.get("scroll_on_keystroke", True):
            pass

    # ── Callbacks ──────────────────────────────────────────────

    def _on_child_exited(self, terminal, status):
        self._pid = -1
        try:
            code = os.waitstatus_to_exitcode(status)
        except (AttributeError, ValueError):
            code = status >> 8
        self._vte.feed(f"\r\n\x1b[33m[Process exited with code {code}]\x1b[0m\r\n".encode("utf-8"))
        GLib.idle_add(self._window.close_tab_signal)

    def _on_selection_changed(self, terminal):
        if self._settings.get("auto_copy_selection", True) and terminal.get_has_selection():
            terminal.copy_clipboard_format(Vte.Format.TEXT)

    def _get_visible_text(self, num_lines):
        text = self._vte.get_text(True, None, None) or ""
        lines = text.split("\n")
        if len(lines) > num_lines:
            lines = lines[-num_lines:]
        return "\n".join(lines)

    def _on_button_press(self, terminal, event):
        if event.button == 3:
            self._show_context_menu(event)
            return True
        if event.button == 1:
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
            url = self._url_at_position(int(event.x), int(event.y))
            if url and (ctrl or not terminal.get_has_selection()):
                self._open_url(url)
                return True
        return False

    def _url_at_position(self, x, y):
        try:
            result = self._vte.translate_coordinates(x, y)
        except Exception:
            return None
        if not result:
            return None
        if isinstance(result, tuple):
            if len(result) == 3:
                success, col, row = result
                if not success or col < 0 or row < 0:
                    return None
            elif len(result) == 2:
                col, row = result
                if col < 0 or row < 0:
                    return None
            else:
                return None
        else:
            return None

        tag = self._vte.match_check(int(col), int(row))
        if tag < 0:
            return None

        full_text = self._vte.get_text(True, None, None) or ""
        lines = full_text.split("\n")
        if row < len(lines):
            line_text = lines[row]
        else:
            return None

        url_match = GLib.Regex.new(
            r'(https?://|ssh://|ftp://|git@|www\.)[\w\.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
            GLib.RegexCompileFlags.CASELESS, 0)
        match_info = url_match.match(line_text, 0)
        if not match_info:
            return None
        start, end = match_info.fetch_pos()
        url = line_text[start:end]

        col_int = int(col)
        if col_int < start or col_int > end:
            offset = 0
            while True:
                match_info = url_match.match(line_text, offset)
                if not match_info:
                    break
                s, e = match_info.fetch_pos()
                if s <= col_int <= e:
                    return line_text[s:e]
                offset = e
            return None
        return url

    def _open_url(self, url):
        if not url:
            return
        if url.startswith("www.") and not url.startswith("http"):
            url = "http://" + url
        subprocess.Popen(["xdg-open", url], start_new_session=True)

    def _show_context_menu(self, event):
        menu = Gtk.Menu()

        copy_item = Gtk.MenuItem(label="Copy")
        copy_item.set_sensitive(self._vte.get_has_selection())
        copy_item.connect("activate", lambda _: self.copy())
        menu.append(copy_item)

        paste_item = Gtk.MenuItem(label="Paste")
        paste_item.connect("activate", lambda _: self.paste())
        menu.append(paste_item)

        menu.append(Gtk.SeparatorMenuItem())

        has_sel = self._vte.get_has_selection()
        add_note_item = Gtk.MenuItem(label="Add to Note")
        add_note_item.set_sensitive(has_sel)
        add_note_item.set_tooltip_text("Append the selected text to a notes file")
        if has_sel:
            add_note_item.connect("activate", lambda _: self._add_selection_to_note())
        menu.append(add_note_item)

        menu.append(Gtk.SeparatorMenuItem())

        fm_item = Gtk.MenuItem(label="Open File Manager Here")
        fm_item.connect("activate", lambda _: self._open_fm())
        menu.append(fm_item)

        menu.append(Gtk.SeparatorMenuItem())

        sel_all_item = Gtk.MenuItem(label="Select All")
        sel_all_item.connect("activate", lambda _: self.select_all())
        menu.append(sel_all_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _add_selection_to_note(self):
        self._vte.copy_clipboard_format(Vte.Format.TEXT)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if not text:
            return
        path = self._notes.write_note(text)
        self._vte.feed(
            f"\r\n\x1b[32m+ Added selection to note: {path}\x1b[0m\r\n".encode()
        )
        self._vte.feed_child(b'\r')

    def _open_fm(self):
        from tpgk.window import _detect_file_manager
        fm = _detect_file_manager(self._settings)
        if not fm:
            return
        cwd = self.get_cwd()
        import subprocess
        subprocess.Popen([fm, cwd], start_new_session=True)

    def _is_tpgk_command(self, shadow: str) -> bool:
        return shadow.startswith(_TPGK_PREFIXES)

    def _on_key_press(self, terminal, event):
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(state & Gdk.ModifierType.MOD1_MASK)
        key = event.keyval

        if ctrl and shift:
            if key == Gdk.KEY_C or key == Gdk.KEY_c:
                self.copy()
                return True
            if key == Gdk.KEY_V or key == Gdk.KEY_v:
                self.paste()
                return True
            if key == Gdk.KEY_W or key == Gdk.KEY_w:
                self._window.close_tab_signal()
                return True
            if key == Gdk.KEY_N or key == Gdk.KEY_n:
                self._window.new_tab_signal()
                return True
            if key == Gdk.KEY_T or key == Gdk.KEY_t:
                self._window.new_tab_signal()
                return True
            if key == Gdk.KEY_Q or key == Gdk.KEY_q:
                self._window.close_window_signal()
                return True
            if key == Gdk.KEY_S or key == Gdk.KEY_s:
                self._window.set_title_dialog()
                return True
            if key == Gdk.KEY_R or key == Gdk.KEY_r:
                self._window.reset_terminal()
                return True
            if key == Gdk.KEY_X or key == Gdk.KEY_x:
                self._window.reset_and_clear()
                return True
            if key == Gdk.KEY_A or key == Gdk.KEY_a:
                self.select_all()
                return True
            if key == Gdk.KEY_E or key == Gdk.KEY_e:
                self._window.split_signal("vertical")
                return True
            if key == Gdk.KEY_D or key == Gdk.KEY_d:
                self._window.split_signal("horizontal")
                return True

        if ctrl and not shift:
            if key == Gdk.KEY_R or key == Gdk.KEY_r:
                self._start_history_search()
                return True
            if key == Gdk.KEY_D or key == Gdk.KEY_d:
                if self._pid == -1:
                    self._window.close_tab_signal()
                elif self._pty_fd >= 0:
                    try:
                        os.write(self._pty_fd, b'\x04')
                    except OSError:
                        self.feed_command_bytes(b'\x04')
                else:
                    self.feed_command_bytes(b'\x04')
                return True
            if key == Gdk.KEY_L or key == Gdk.KEY_l:
                self.feed_command_bytes(b'\x0c')
                return True
            if key == Gdk.KEY_U or key == Gdk.KEY_u:
                self.feed_command_bytes(b'\x15')
                self._input_shadow = ""
                return True
            if key == Gdk.KEY_W or key == Gdk.KEY_w:
                self.feed_command_bytes(b'\x17')
                parts = self._input_shadow.rsplit(' ', 1)
                self._input_shadow = parts[0] if len(parts) > 1 else ""
                return True
            if key == Gdk.KEY_C or key == Gdk.KEY_c:
                self.feed_command_bytes(b'\x03')
                self._input_shadow = ""
                self._ai_mode = False
                self._ai_generation += 1
                self._ai_busy = False
                self._provider_list = []
                self._model_list = []
                self._async_pending = False
                return True
            if key == Gdk.KEY_plus or key == Gdk.KEY_equal:
                self.zoom_in()
                return True
            if key == Gdk.KEY_minus:
                self.zoom_out()
                return True
            if key == Gdk.KEY_0:
                self.zoom_reset()
                return True

        if ctrl and alt:
            if key == Gdk.KEY_O or key == Gdk.KEY_o:
                self._window.focus_other_pane_signal()
                return True

        if alt and not ctrl:
            num = key - Gdk.KEY_0
            if 1 <= num <= 9:
                self._replay_history_number(num)
                return True

        if self._ai_mode and not ctrl:
            if key == Gdk.KEY_Escape:
                self._ai_mode = False
                self._ai_input = ""
                self.feed_command_bytes(b'\x15')
                self._vte.feed(b'\r\n')
                return True
            if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                question = self._ai_input.strip()
                self._ai_input = ""
                if question == "/ai off":
                    self._ai_mode = False
                    self._ai_client = None
                    self._vte.feed(b"\r\n\x1b[33m[AI Chat Ended]\x1b[0m\r\n")
                    return True
                self._vte.feed(b'\r\n')
                if question:
                    self._ask_ai_stream(question)
                return True
            if key == Gdk.KEY_BackSpace:
                if self._ai_input:
                    self._ai_input = self._ai_input[:-1]
                    self._vte.feed(b'\b \b')
                return True
            text = event.string
            if text and len(text) == 1 and ord(text[0]) >= 0x20:
                self._ai_input += text
                self._vte.feed(text.encode())
                return True
            return False

        if self._history_search_mode:
            self._handle_history_search_key(event)
            return True

        if self._async_pending:
            if key == Gdk.KEY_Escape:
                self._cancel_async_wait()
            return True

        if self._provider_list or self._model_list or self._history_show_results:
            text = event.string
            if key == Gdk.KEY_Escape:
                self._provider_list = []
                self._model_list = []
                self._history_show_results = []
                self._async_pending = False
                self._vte.feed(b"\r\n\x1b[37mSelection cancelled.\x1b[0m\r\n")
                self._input_shadow = ""
                return True
            if text and text.isdigit():
                num = int(text)
                if 1 <= num <= 9:
                    if self._provider_list:
                        self._select_provider_number(num)
                    elif self._model_list:
                        self._select_model_number(num)
                    elif self._history_show_results:
                        self._replay_history_number(num)
                    if self._provider_list or self._model_list or self._history_show_results or self._async_pending:
                        return True
                    self._input_shadow = ""
                    return True
            self._provider_list = []
            self._model_list = []
            self._history_show_results = []
            self._input_shadow = ""
            return True

        if key == Gdk.KEY_Tab and self._input_shadow.startswith('/'):
            self._autocomplete_tpgk()
            return True

        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            shadow = self._input_shadow.strip()
            if shadow:
                # Fix #6: record the shell's cwd, not the tpgk process cwd
                self._history.add(shadow, self.get_cwd())
                # Fix #2: clear bash readline buffer before handling a TPGK command,
                # because regular chars already landed in bash's readline buffer
                if self._is_tpgk_command(shadow):
                    self.feed_command_bytes(b'\x15')
                if shadow == "/ai off":
                    self._ai_mode = False
                    self._ai_client = None
                    self._vte.feed(b"\r\n\x1b[33m[AI Chat Ended]\x1b[0m\r\n")
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/ai context "):
                    rest = shadow[12:].strip()
                    parts = rest.split(None, 1)
                    if parts and parts[0].isdigit():
                        num_lines = int(parts[0])
                        question = parts[1] if len(parts) > 1 else ""
                        term_text = self._get_visible_text(num_lines)
                        preamble = (
                            f"Context: last {num_lines} lines of terminal output:\n\n"
                            f"```\n{term_text}\n```\n\n"
                        )
                        if question:
                            preamble += f"Question: {question}"
                        else:
                            preamble += "Analyze the context above and summarize it."
                        self._start_ai(preamble)
                        self._input_shadow = ""
                        return True
                    else:
                        self._vte.feed(
                            b"\r\n\x1b[33mUsage: /ai context <N> <question>\x1b[0m\r\n"
                        )
                        self._vte.feed_child(b'\r')
                        self._input_shadow = ""
                        return True
                elif shadow.startswith("/ai ") or shadow.startswith("/ai\t"):
                    self._start_ai(shadow[4:].strip())
                    self._input_shadow = ""
                    return True
                elif shadow == "/ai":
                    self._start_ai("")
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/history") or shadow.startswith("/history "):
                    self._cmd_history(shadow.split(None, 1)[1] if " " in shadow else "")
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/wnotes"):
                    args = shadow.split(None, 1)[1] if " " in shadow else ""
                    self._cmd_wnotes(args)
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/onotes"):
                    args = shadow.split(None, 1)[1] if " " in shadow else ""
                    self._cmd_onotes(args)
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/connect"):
                    args = shadow.split(None, 1)[1] if " " in shadow else ""
                    self._cmd_connect(args)
                    self._input_shadow = ""
                    return True
                elif shadow == "/help":
                    self._cmd_help()
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
                elif shadow == "/clear" or shadow == "/cls":
                    self._vte.feed(b'\033[H\033[2J')
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
            self._input_shadow = ""

        if key == Gdk.KEY_BackSpace:
            bs = self._settings.get("backspace_binding", "ascii-del")
            if bs == "control-h":
                self.feed_command_bytes(b'\x08')
            elif bs == "escape-sequence":
                self.feed_command_bytes(b'\x1b\x7f')
            else:
                self.feed_command_bytes(b'\x7f')
            if self._input_shadow:
                self._input_shadow = self._input_shadow[:-1]
            return True

        if key == Gdk.KEY_Delete:
            dl = self._settings.get("delete_binding", "escape-sequence")
            if dl == "ascii-del":
                self.feed_command_bytes(b'\x7f')
            elif dl == "control-h":
                self.feed_command_bytes(b'\x08')
            else:
                self.feed_command_bytes(b'\x1b[3~')
            return True

        text = event.string
        if text and len(text) == 1:
            if ord(text[0]) >= 0x20 or key == Gdk.KEY_Tab:
                self._input_shadow += text if key != Gdk.KEY_Tab else "\t"

        return False

    def _on_title_changed(self, terminal):
        title = terminal.get_window_title()
        if not title:
            return
        self._window.set_tab_title_from_terminal(self, title)

    def _on_contents_changed(self, terminal):
        pass

    def _show_command_bar(self):
        if self._cmd_bar_visible:
            return
        self._cmd_bar_visible = True
        self._cmd_bar_revealer.set_reveal_child(True)
        self._cmd_entry.set_text("/")
        self._cmd_entry.set_position(-1)
        self._build_cmd_list("")
        self._cmd_entry.grab_focus()

    def _hide_command_bar(self):
        self._cmd_bar_visible = False
        self._cmd_bar_revealer.set_reveal_child(False)
        self._input_shadow = ""
        self._vte.grab_focus()

    def _on_cmd_bar_changed(self, entry):
        self._build_cmd_list(entry.get_text())

    def _build_cmd_list(self, query):
        for child in self._cmd_list.get_children():
            self._cmd_list.remove(child)
        q = query.lower().lstrip('/')
        first = None
        for cmd, desc in self._cmd_commands:
            if not q or q in cmd.lower():
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                lbl = Gtk.Label(label=f"{cmd}  ")
                lbl.set_xalign(0)
                lbl.set_halign(Gtk.Align.START)
                attrs = Pango.AttrList()
                attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
                lbl.set_attributes(attrs)
                desc_lbl = Gtk.Label(label=desc)
                desc_lbl.set_xalign(0)
                desc_lbl.set_halign(Gtk.Align.START)
                desc_lbl.get_style_context().add_class("dim-label")
                hbox.pack_start(lbl, False, False, 0)
                hbox.pack_start(desc_lbl, True, True, 0)
                row.add(hbox)
                row.show_all()
                self._cmd_list.add(row)
                if first is None:
                    first = row
        if first:
            self._cmd_list.select_row(first)

    def _on_cmd_bar_row_activated(self, listbox, row):
        if hasattr(row, 'cmd_data'):
            cmd = row.cmd_data
            self._vte.feed_child((cmd + "\n").encode("utf-8"))
            self._history.add(cmd, self.get_cwd())
            self._hide_command_bar()
            return
        children = row.get_children()
        if children:
            box = children[0]
            labels = box.get_children()
            if labels:
                cmd_label = labels[0].get_text().strip()
                self._cmd_entry.set_text(cmd_label + " ")
                self._cmd_entry.set_position(-1)
                self._cmd_entry.grab_focus()

    def _on_cmd_bar_activated(self, entry):
        self._execute_from_bar()

    def _execute_from_bar(self):
        shadow = self._cmd_entry.get_text().strip()
        if not shadow:
            self._hide_command_bar()
            return
        self._hide_command_bar()
        self._input_shadow = shadow
        self._execute_tpgk_command(shadow)
        self._input_shadow = ""

    def _on_cmd_bar_key(self, entry, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self._hide_command_bar()
            return True
        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            sel = self._cmd_list.get_selected_row()
            if sel and hasattr(sel, 'cmd_data'):
                cmd = sel.cmd_data
                self._vte.feed_child((cmd + "\n").encode("utf-8"))
                self._history.add(cmd, self.get_cwd())
                self._hide_command_bar()
                return True
            return False
        if key == Gdk.KEY_Down:
            children = self._cmd_list.get_children()
            if children:
                sel = self._cmd_list.get_selected_row()
                idx = sel.get_index() if sel else -1
                nxt = children[(idx + 1) % len(children)]
                self._cmd_list.select_row(nxt)
            return True
        if key == Gdk.KEY_Up:
            children = self._cmd_list.get_children()
            if children:
                sel = self._cmd_list.get_selected_row()
                idx = sel.get_index() if sel else len(children)
                prev = children[(idx - 1) % len(children)]
                self._cmd_list.select_row(prev)
            return True
        if key == Gdk.KEY_Tab:
            children = self._cmd_list.get_children()
            if children:
                sel = self._cmd_list.get_selected_row()
                if sel and hasattr(sel, 'cmd_data'):
                    self._cmd_entry.set_text(sel.cmd_data)
                    self._cmd_entry.set_position(-1)
                    return True
                row = sel or children[0]
                box = row.get_children()[0]
                cmd_label = box.get_children()[0].get_text().strip()
                self._cmd_entry.set_text(cmd_label + " ")
                self._cmd_entry.set_position(-1)
            return True
        return False

    def _execute_tpgk_command(self, shadow):
        self._history.add(shadow, self.get_cwd())
        self.feed_command_bytes(b'\x15')
        if shadow == "/ai off":
            self._ai_mode = False
            self._ai_client = None
            self._vte.feed(b"\r\n\x1b[33m[AI Chat Ended]\x1b[0m\r\n")
        elif shadow.startswith("/ai context "):
            rest = shadow[12:].strip()
            parts = rest.split(None, 1)
            if parts and parts[0].isdigit():
                num_lines = int(parts[0])
                question = parts[1] if len(parts) > 1 else ""
                term_text = self._get_visible_text(num_lines)
                preamble = (
                    f"Context: last {num_lines} lines of terminal output:\n\n"
                    f"```\n{term_text}\n```\n\n"
                )
                if question:
                    preamble += f"Question: {question}"
                else:
                    preamble += "Analyze the context above and summarize it."
                self._start_ai(preamble)
            else:
                self._vte.feed(
                    b"\r\n\x1b[33mUsage: /ai context <N> <question>\x1b[0m\r\n"
                )
        elif shadow.startswith("/ai ") or shadow.startswith("/ai\t"):
            self._start_ai(shadow[4:].strip())
        elif shadow == "/ai":
            self._start_ai("")
        elif shadow.startswith("/history"):
            self._cmd_history(shadow.split(None, 1)[1] if " " in shadow else "")
        elif shadow.startswith("/wnotes"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_wnotes(args)
        elif shadow.startswith("/onotes"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_onotes(args)
        elif shadow.startswith("/connect"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_connect(args)
        elif shadow == "/help":
            self._cmd_help()
        elif shadow in ("/clear", "/cls"):
            self._vte.feed(b'\033[H\033[2J')

    # ── Tab autocomplete ─────────────────────────────────────

    def _autocomplete_tpgk(self):
        if not self._input_shadow.startswith('/'):
            return
        shadow = self._input_shadow[1:]
        if ' ' in shadow and shadow.startswith('connect'):
            self._autocomplete_connect_arg(shadow)
            return
        partial = shadow
        matches = [c for c in TPGK_COMMANDS if c.startswith(partial)]
        if len(matches) == 1:
            self.feed_command_bytes(b'\x15')
            completed = '/' + matches[0] + ' '
            self._input_shadow = completed
            self._vte.feed_child(completed.encode())
        elif len(matches) > 1:
            common = os.path.commonprefix(matches)
            if len(common) > len(partial):
                self.feed_command_bytes(b'\x15')
                completed = '/' + common
                self._input_shadow = completed
                self._vte.feed_child(completed.encode())
            else:
                self.feed_command_bytes(b'\x15')
                self._vte.feed(
                    f"\r\n\x1b[90m{'  '.join('/' + m for m in matches)}\x1b[0m\r\n".encode()
                )
                self._vte.feed_child(self._input_shadow.encode())

    def _autocomplete_connect_arg(self, shadow):
        parts = shadow.split(None, 1)
        arg = parts[1] if len(parts) > 1 else ""
        providers = sorted(AIClient.PROVIDERS.keys())
        matches = [p for p in providers if p.startswith(arg)]
        if len(matches) == 1:
            self.feed_command_bytes(b'\x15')
            completed = '/connect ' + matches[0] + ' '
            self._input_shadow = completed
            self._vte.feed_child(completed.encode())
        else:
            self.feed_command_bytes(b'\x15')
            self._show_provider_list()

    # ── AI ────────────────────────────────────────────────────

    def _start_ai(self, prompt=""):
        self._ai_mode = True
        self._ai_input = ""

        provider = self._settings.get("ai_last_provider", "") or self._settings.get("ai_provider", "")
        if not provider:
            self._vte.feed(b"\r\n\x1b[31m[AI] No provider configured. Use Preferences > AI or /connect.\x1b[0m\r\n")
            self._ai_mode = False
            return

        keys = self._settings.get("ai_keys", {})
        models = self._settings.get("ai_models", {})
        urls = self._settings.get("ai_urls", {})
        api_key = keys.get(provider, "")
        model = models.get(provider, "")
        base_url = urls.get(provider, "")

        if not api_key and provider not in ("ollama", "custom"):
            self._vte.feed(b"\r\n\x1b[31m[AI] No API key configured for this provider.\x1b[0m\r\n")
            self._ai_mode = False
            return

        try:
            self._ai_client = AIClient(provider, api_key, model or None, base_url)
            sys_prompts = self._settings.get("ai_system_prompts", {})
            sys_prompt = sys_prompts.get(provider, "")
            if sys_prompt:
                self._ai_client.set_system_prompt(sys_prompt)
            self._ai_client.reset()
        except Exception as e:
            self._vte.feed(f"\r\n\x1b[31m[AI] Error: {e}\x1b[0m\r\n".encode())
            self._ai_mode = False
            return

        info = AIClient.PROVIDERS[provider]
        self._vte.feed(
            f"\r\n\x1b[35m=== AI Chat Mode: {info['name']} ({self._ai_client.model}) ===\x1b[0m\r\n".encode()
        )
        self._vte.feed(b"\x1b[90mType your message and press Enter. Type /ai off to exit.\x1b[0m\r\n\r\n")

        if prompt:
            self._ask_ai_stream(prompt)

    def _ask_ai_stream(self, question: str):
        if not self._ai_client:
            return
        if self._ai_busy:
            self._vte.feed(b'\x1b[33mStill waiting for a reply...\x1b[0m\r\n')
            return
        self._ai_busy = True
        self._vte.feed('\x1b[33m● Thinking\x1b[0m'.encode('utf-8'))
        self._ai_generation += 1
        gen = self._ai_generation
        threading.Thread(target=self._run_ai_stream, args=(question, gen), daemon=True).start()

    def _run_ai_stream(self, question, gen):
        first_token = True
        try:
            for chunk in self._ai_client.chat_stream(question):
                if not self._ai_mode or self._ai_generation != gen:
                    break
                if first_token:
                    first_token = False
                    GLib.idle_add(lambda g=gen: (self._vte.feed(b'\r\x1b[K')
                                         if self._ai_generation == g and self._ai_mode else None))
                GLib.idle_add(
                    lambda data=chunk.encode("utf-8"), g=gen:
                        (self._vte.feed(data)
                         if self._ai_generation == g and self._ai_mode else None))
        except Exception as e:
            if self._ai_mode and self._ai_generation == gen:
                GLib.idle_add(
                    lambda err=str(e), g=gen:
                        (self._vte.feed(
                            f"\r\n\x1b[31m[AI Error] {err}\x1b[0m\r\n".encode())
                         if self._ai_generation == g else None)
                )
        GLib.idle_add(lambda g=gen: self._on_ai_finished(g) if self._ai_generation == g else None)

    def _on_ai_finished(self, gen=None):
        if gen is not None and self._ai_generation != gen:
            return
        self._ai_busy = False
        if self._ai_mode:
            self._vte.feed(b'\r\n\r\n')

    # ── History search ────────────────────────────────────────

    def _start_history_search(self):
        self._history_search_mode = True
        self._history_search_query = ""
        self._history_search_index = -1
        self._history_search_results = self._history.interactive_search("")
        self._show_search_results()

    def _handle_history_search_key(self, event):
        key = event.keyval
        text = event.string

        if key == Gdk.KEY_Escape:
            if self._history_list_display:
                self._vte.feed(b'\033[?1049l')
            self._history_search_mode = False
            self._history_list_display = False
            self._history_search_query = ""
            self._history_search_results = []
            self._history_list_results = []
            self._history_list_index = 0
            self._history_list_nlines = 0
            self._vte.feed(b'\r\n')
            return

        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            if self._history_list_display:
                self._vte.feed(b'\033[?1049l')
                self._history_search_mode = False
                self._history_list_display = False
                if self._history_list_results and 0 <= self._history_list_index < len(self._history_list_results):
                    cmd = self._history_list_results[self._history_list_index][1]
                    self._vte.feed_child((cmd + "\n").encode("utf-8"))
                    self._history.add(cmd, self.get_cwd())
                else:
                    self._vte.feed(b'\r\n')
                self._history_search_query = ""
                self._history_list_results = []
                self._history_list_index = 0
                self._history_list_nlines = 0
                return

            self._history_search_mode = False
            if self._history_search_results and self._history_search_index >= 0:
                cmd = self._history_search_results[self._history_search_index][0]
                self._vte.feed_child((cmd + "\n").encode("utf-8"))
                self._history.add(cmd, self.get_cwd())
            else:
                self._vte.feed(b'\r\n')
            self._history_search_query = ""
            self._history_search_results = []
            return

        if self._history_list_display:
            if key == Gdk.KEY_Up:
                if self._history_list_results and self._history_list_index > 0:
                    self._history_list_index -= 1
                    self._show_history_list()
                return

            if key == Gdk.KEY_Down:
                if self._history_list_results and self._history_list_index < len(self._history_list_results) - 1:
                    self._history_list_index += 1
                    self._show_history_list()
                return

            if key == Gdk.KEY_BackSpace:
                if self._history_search_query:
                    self._history_search_query = self._history_search_query[:-1]
            elif text and len(text) == 1 and ord(text[0]) >= 0x20:
                self._history_search_query += text

            self._history_list_index = 0
            self._history_list_results = self._history.search(self._history_search_query, 50)
            self._history_search_results = [(cmd,) for _, cmd, _, _ in self._history_list_results] if self._history_list_results else []
            self._show_history_list()
            return

        if key == Gdk.KEY_Up:
            if self._history_search_results:
                self._history_search_index = min(
                    self._history_search_index + 1,
                    len(self._history_search_results) - 1,
                )
                self._show_search_results()
            return

        if key == Gdk.KEY_Down:
            if self._history_search_results:
                self._history_search_index = max(self._history_search_index - 1, -1)
                if self._history_search_index < 0:
                    self._vte.feed(b'\r\033[K')
                    self._vte.feed(f"\r\x1b[90m(query)> {self._history_search_query}\x1b[0m".encode())
                else:
                    self._show_search_results()
            return

        if key == Gdk.KEY_BackSpace:
            if self._history_search_query:
                self._history_search_query = self._history_search_query[:-1]
        elif text and len(text) == 1 and ord(text[0]) >= 0x20:
            self._history_search_query += text
            self._history_search_index = -1

        self._history_search_results = self._history.interactive_search(self._history_search_query)
        self._show_search_results()

    def _show_search_results(self):
        self._vte.feed(b'\r\033[K')
        if self._history_search_index >= 0 and self._history_search_index < len(self._history_search_results):
            selected = self._history_search_results[self._history_search_index][0]
            self._vte.feed(f"\r\x1b[92m> {selected}\x1b[0m".encode())
        elif self._history_search_results:
            preview = self._history_search_results[0][0]
            count = len(self._history_search_results)
            self._vte.feed(
                f"\r\x1b[44m\x1b[37m(reverse-i-search)`{self._history_search_query}`: {count}\x1b[0m  \x1b[33m{preview[:60]}\x1b[0m".encode()
            )
        else:
            self._vte.feed(
                f"\r\x1b[44m\x1b[37m(reverse-i-search)`{self._history_search_query}`: 0\x1b[0m".encode()
            )

    def _show_history_list(self):
        results = self._history_list_results
        if not results:
            out = ""
            if self._history_search_query:
                out += f"\x1b[33mNo results for: {self._history_search_query}\x1b[0m\r\n"
            else:
                out += "\x1b[33mNo history found.\x1b[0m\r\n"
            out += "\x1b[90mType to filter, Esc to cancel.\x1b[0m\r\n"
            self._history_list_nlines = out.count('\n')
            self._vte.feed(f"\033[2J\033[H{out}".encode())
            return

        total = len(results)
        per_page = 10
        page_start = (self._history_list_index // per_page) * per_page
        page_end = min(total, page_start + per_page)

        out = "\x1b[36m─── History ───\x1b[0m\r\n"
        for i in range(page_start, page_end):
            _, cmd, _, ts = results[i]
            time_str = ts[-8:] if ts else ""
            display = cmd[:100] + ("..." if len(cmd) > 100 else "")

            if i == self._history_list_index:
                out += f"\x1b[92m \u25b6 \x1b[0m{display}  \x1b[90m{time_str}\x1b[0m\r\n"
            else:
                out += f"  {display}  \x1b[90m{time_str}\x1b[0m\r\n"

        query_disp = f"'{self._history_search_query}'" if self._history_search_query else "all"
        out += (
            f"\x1b[90m─── {total} matches for {query_disp} — "
            f"\u2191\u2193 select, type to filter, Enter execute, Esc cancel\x1b[0m"
        )
        self._history_list_nlines = out.count('\n')
        self._vte.feed(f"\033[2J\033[H{out}".encode())

    def _replay_history_number(self, num: int):
        results = self._history.interactive_search("", 20)
        if 0 <= num - 1 < len(results):
            cmd = results[num - 1][0]
            # Fix #11: \x1b[K is a display escape, meaningless as pty input; use \x15 to kill readline
            self._vte.feed_child(b'\x15')
            self._vte.feed_child(cmd.encode("utf-8"))

    # ── TPGK commands ──────────────────────────────────────────

    def _cmd_history(self, args=""):
        self._history_list_display = True
        self._history_search_mode = True
        self._history_search_query = args.strip() if args else ""
        self._history_search_index = 0
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._vte.feed(b'\033[?1049h')
        self._history_list_results = self._history.search(self._history_search_query, 50)
        self._history_search_results = [(cmd,) for _, cmd, _, _ in self._history_list_results] if self._history_list_results else []
        self._show_history_list()

    def _cmd_wnotes(self, args=""):
        if not args:
            self._vte.feed(b"\r\n\x1b[33mUsage: /wnotes [-filename.md] <note text>\x1b[0m\r\n")
            return
        # Fix #12: parse optional -filename flag
        filename = None
        text = args
        if args.startswith("-"):
            filename, _, text = args[1:].partition(" ")
            text = text.strip()
            if not text:
                self._vte.feed(b"\r\n\x1b[33mUsage: /wnotes [-filename.md] <note text>\x1b[0m\r\n")
                return
        path = self._notes.write_note(text, filename or None)
        self._vte.feed(f"\r\n\x1b[32mNote saved to: {path}\x1b[0m\r\n".encode())

    def _cmd_onotes(self, args=""):
        # Fix #12: parse optional -filename flag (previously the dash was included in the filename)
        filename = None
        if args.strip():
            a = args.strip()
            filename = a[1:] if a.startswith("-") else a
        path = self._notes.open_notes(filename or None)
        self._vte.feed(f"\r\n\x1b[32mOpening notes: {path}\x1b[0m\r\n".encode())

    def _cmd_connect(self, args=""):
        if not args:
            self._show_provider_list()
            return

        parts = args.split()
        provider = parts[0].lower()
        if provider not in AIClient.PROVIDERS:
            valid = "|".join(AIClient.PROVIDERS.keys())
            self._vte.feed(f"\r\n\x1b[31mInvalid provider: {provider}\x1b[0m\r\n".encode())
            self._vte.feed(f"\x1b[90mUse: /connect [{valid}]\x1b[0m\r\n".encode())
            return

        self._connect_to_provider(provider)

    def _show_provider_list(self):
        self._vte.feed(b"\r\n\x1b[90mChecking configured providers...\x1b[0m\r\n")
        self._async_pending = True
        threading.Thread(target=self._compute_provider_list_thread, daemon=True).start()

    def _compute_provider_list_thread(self):
        keys = self._settings.get("ai_keys", {})
        models = self._settings.get("ai_models", {})
        urls = self._settings.get("ai_urls", {})
        available = []

        for provider in ["openai", "claude", "gemini", "deepseek", "ollama", "custom"]:
            info = AIClient.PROVIDERS[provider]
            if provider in ("ollama", "custom"):
                url = urls.get(provider, "") or info["url"]
                if AIClient.ping_provider(provider, url):
                    fetched = AIClient.fetch_models(provider, "", url)
                    model = models.get(provider, "") or (fetched[0] if fetched else info["default_model"])
                    label = f"{info['name']} ({model})"
                    if fetched:
                        label += f" [{len(fetched)} models]"
                    available.append((provider, label, info, fetched))
            else:
                key = keys.get(provider, "")
                if key:
                    model = models.get(provider, "") or info["default_model"]
                    label = f"{info['name']} ({model})"
                    available.append((provider, label, info, []))

        GLib.idle_add(lambda: self._on_provider_list_ready(available))

    def _on_provider_list_ready(self, available):
        self._async_pending = False

        if not available:
            self._vte.feed(b"\x1b[33mNo providers configured.\x1b[0m\r\n")
            self._vte.feed(b"\x1b[90mSet API keys in Preferences > AI.\x1b[0m\r\n")
            self._input_shadow = ""
            return

        out = "\r\n\x1b[36mAvailable providers:\x1b[0m\r\n"
        self._provider_list = []
        for i, (prov, label, info, fetched) in enumerate(available[:9]):
            num = i + 1
            icon = "\x1b[32m●\x1b[0m" if prov != "custom" or fetched else "\x1b[33m●\x1b[0m"
            out += f"  \x1b[33m[{num}]\x1b[0m {icon} {label}\r\n"
            self._provider_list.append((num, prov, fetched))
        out += "\x1b[90mPress 1..9 to select a provider, Esc to cancel.\x1b[0m\r\n"
        self._vte.feed(out.encode())

    def _cancel_async_wait(self):
        self._async_pending = False
        self._provider_list = []
        self._model_list = []
        self._history_show_results = []
        self._vte.feed(b"\r\n\x1b[37mCancelled.\x1b[0m\r\n")
        self._input_shadow = ""

    def _select_provider_number(self, num):
        for n, prov, fetched in self._provider_list:
            if n == num:
                self._provider_list = []
                self._connect_to_provider(prov)
                return
        self._provider_list = []

    def _connect_to_provider(self, provider):
        key = self._settings.get("ai_keys", {}).get(provider, "")
        model = self._settings.get("ai_models", {}).get(provider, "")
        base_url = self._settings.get("ai_urls", {}).get(provider, "")
        info = AIClient.PROVIDERS[provider]

        if provider not in ("ollama", "custom") and not key:
            self._vte.feed(f"\r\n\x1b[33mNo API key set for {provider}.\x1b[0m\r\n".encode())
            return

        self._connect_provider = provider
        self._connect_key = key
        self._connect_url = base_url
        self._connect_model = model

        self._vte.feed(f"\r\n\x1b[90mConnecting to {info['name']}...\x1b[0m\r\n".encode())
        self._async_pending = True
        threading.Thread(
            target=self._fetch_models_thread,
            args=(provider, key, model, base_url),
            daemon=True,
        ).start()

    def _fetch_models_thread(self, provider, key, model, base_url):
        models = AIClient.fetch_models(provider, key, base_url)
        GLib.idle_add(lambda: self._on_models_fetched(provider, key, model, base_url, models))

    def _on_models_fetched(self, provider, key, model, base_url, models):
        self._async_pending = False

        if models and len(models) > 1:
            info = AIClient.PROVIDERS[provider]
            out = f"\r\n\x1b[36m{info['name']} — {len(models)} models:\x1b[0m\r\n"
            self._model_list = []
            for i, m in enumerate(models[:9]):
                num = i + 1
                marker = " \x1b[32m(current)\x1b[0m" if m == model else ""
                out += f"  \x1b[33m[{num}]\x1b[0m {m}{marker}\r\n"
                self._model_list.append((num, m))
            out += "\x1b[90mPress 1..9 to select, any other key for default.\x1b[0m\r\n"
            self._vte.feed(out.encode())
        else:
            chosen = models[0] if models else model
            self._do_connect(provider, key, chosen, base_url, feed_prompt=True)

    def _select_model_number(self, num):
        for n, m in self._model_list:
            if n == num:
                self._model_list = []
                self._do_connect(self._connect_provider, self._connect_key, m, self._connect_url, feed_prompt=True)
                return
        self._model_list = []

    def _do_connect(self, provider, api_key, model, base_url, feed_prompt=False):
        try:
            self._ai_client = AIClient(provider, api_key, model if model else None, base_url)
            self._settings.set("ai_last_provider", provider)
            self._settings.set("ai_provider", provider)
            if model:
                models = self._settings.get("ai_models", {})
                models[provider] = model
                self._settings.set("ai_models", models)
            if base_url:
                urls = self._settings.get("ai_urls", {})
                urls[provider] = base_url
                self._settings.set("ai_urls", urls)
            info = AIClient.PROVIDERS[provider]
            self._vte.feed(
                f"\r\n\x1b[32m✓ Connected to {info['name']} ({self._ai_client.model})\x1b[0m\r\n".encode()
            )
            self._vte.feed(b"\x1b[90mType /ai to start chatting.\x1b[0m\r\n")
            if feed_prompt:
                self._vte.feed_child(b'\r')
        except Exception as e:
            self._vte.feed(f"\r\n\x1b[31mFailed to connect: {e}\x1b[0m\r\n".encode())

    def _cmd_help(self):
        help_text = (
            "\r\n\x1b[36m─── TPGK Commands ───\x1b[0m\r\n"
            "  \x1b[33m/history\x1b[0m [terms]       Search command history\r\n"
            "  \x1b[33m/ai\x1b[0m                   Enter AI chat mode\r\n"
            "  \x1b[33m/ai off\x1b[0m               Exit AI chat mode\r\n"
            "  \x1b[33m/ai context N q\x1b[0m       Include last N terminal lines as context\r\n"
            "  \x1b[33m/connect\x1b[0m [prov]        Connect to AI provider\r\n"
            "  \x1b[33m/wnotes\x1b[0m [-file] txt    Save a timestamped note\r\n"
            "  \x1b[33m/onotes\x1b[0m [-file]         Open notes in editor\r\n"
            "  \x1b[33m/help\x1b[0m                  Show this help\r\n"
            "  \x1b[33m/clear\x1b[0m                 Clear the screen\r\n"
            "\r\n"
            "  \x1b[90mTab\x1b[0m                    Autocomplete /commands\r\n"
            "  \x1b[90mCtrl+R\x1b[0m                  History search\r\n"
            "  \x1b[90mCtrl+U\x1b[0m                  Kill line\r\n"
            "  \x1b[90mCtrl+W\x1b[0m                  Kill word\r\n"
            "  \x1b[90mCtrl+Click\x1b[0m              Open URL in browser\r\n"
            "  \x1b[90mCtrl+Shift+C/V\x1b[0m          Copy / Paste\r\n"
            "  \x1b[90mCtrl+Shift+T/N\x1b[0m          New Tab / Window\r\n"
            "  \x1b[90mAlt+1..9\x1b[0m                Replay history\r\n"
            "\x1b[36m─────────────────────────\x1b[0m\r\n"
        )
        self._vte.feed(help_text.encode())



def _hex_to_gdk(hex_color: str):
    color = Gdk.RGBA()
    color.parse(hex_color)
    return color
