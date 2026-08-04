import os
import gc
import gi
import threading
import subprocess
import re
import shutil
import sqlite3
import termios

gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, Pango, Vte
from tpgk.settings import Settings
from tpgk.history import HistoryManager
from tpgk.notes import NotesManager
from tpgk.ai_client import AIClient, AIRequestCancelled
from tpgk.logging_utils import get_logger


TPGK_COMMANDS = ["history", "ai", "connect", "wnotes", "onotes", "learn", "optimize", "help", "clear", "cls"]

_TPGK_PREFIXES = ("/ai", "/history", "/wnotes", "/onotes", "/learn", "/optimize", "/connect", "/help", "/clear", "/cls")
logger = get_logger(__name__)

_HINT_CHARS = "asdfghjklqwertyuiopzxcvbnm"

_HINT_URL_RE = re.compile(
    r'(https?://|ssh://|ftp://|git@|www\.)[\w.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
    re.IGNORECASE)

_HINT_PATH_RE = re.compile(
    r'(~?/[\w.\-~+#@!]{2,}(?:/[\w.\-~+#@!]+)*/?)'
    r'|(\./[\w.\-~+#@!]{1,}(?:/[\w.\-~+#@!]+)*/?)')

_HINT_GIT_SHA_RE = re.compile(
    r'\b([0-9a-f]{40}|[0-9a-f]{7,39})\b',
    re.IGNORECASE)

_HINT_IP_RE = re.compile(
    r'\b((?:\d{1,3}\.){3}\d{1,3})\b')


class TerminalBox(Gtk.Box):
    _CMD_COMMANDS = [
        ("/ai", "Enter AI chat mode"),
        ("/ai context N <question>", "Include last N terminal lines as context"),
        ("/ai off", "Exit AI chat mode"),
        ("/connect [provider]", "Connect to AI provider"),
        ("/history [terms | :sql SQL]", "Search command history"),
        ("/wnotes [-file.md] <text>", "Save timestamped note"),
        ("/onotes [-file.md]", "Open notes in editor"),
        ("/help", "Show all commands and shortcuts"),
        ("/clear", "Clear the terminal screen"),
        ("/cls", "Clear the terminal screen"),
    ]

    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._window = window
        self._settings = Settings()
        self._history = HistoryManager()
        self._notes = NotesManager()

        self._vte = Vte.Terminal()
        self._vte.set_scrollback_lines(self._settings.get("scrollback_lines", 10000))
        self._vte.set_mouse_autohide(True)
        # VTE's own scroll-on-output always forces the view to the bottom, even if the
        # user scrolled up to read something. We handle it ourselves in _on_vadj_changed
        # so it only follows new output when the user was already at the bottom.
        self._vte.set_scroll_on_output(False)
        self._vte.set_scroll_on_keystroke(self._settings.get("scroll_on_keystroke", True))
        self._scroll_follow = True

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
        self._apply_padding()

        self._osc133_margin = Gtk.DrawingArea()
        self._osc133_margin.set_size_request(6, -1)
        self._osc133_margin.set_no_show_all(True)
        self._osc133_margin.set_visible(False)
        self._osc133_margin.connect("draw", self._draw_osc133_margin)

        vadj = self._scroll.get_vadjustment()
        if vadj:
            vadj.connect("value-changed", self._on_vadj_value_changed)
            vadj.connect("changed", self._on_vadj_changed)

        term_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        term_box.pack_start(self._osc133_margin, False, False, 0)
        term_box.pack_start(scroll, True, True, 0)

        self._overlay = Gtk.Overlay()
        self._overlay.add(term_box)
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

        self._search_revealer = Gtk.Revealer()
        self._search_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._search_revealer.set_transition_duration(150)
        self._search_revealer.set_halign(Gtk.Align.FILL)
        self._search_revealer.set_valign(Gtk.Align.START)
        self._search_revealer.set_reveal_child(False)
        self._overlay.add_overlay(self._search_revealer)

        self._hints_fixed = Gtk.Fixed()
        self._hints_fixed.set_no_show_all(True)
        self._hints_fixed.hide()
        self._overlay.add_overlay(self._hints_fixed)

        self._vi_overlay_area = Gtk.DrawingArea()
        self._vi_overlay_area.set_no_show_all(True)
        self._vi_overlay_area.hide()
        self._vi_overlay_area.connect("draw", self._draw_vi_overlay)
        self._overlay.add_overlay(self._vi_overlay_area)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        search_box.set_size_request(-1, 32)
        search_frame = Gtk.Frame()
        search_frame.set_shadow_type(Gtk.ShadowType.ETCHED_OUT)
        search_frame.get_style_context().add_class("command-bar-frame")
        search_frame.add(search_box)
        self._search_revealer.add(search_frame)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search scrollback (Enter=next, Shift+Enter=prev, Esc=close)...")
        self._search_entry.connect("search-changed", self._on_search_changed)
        self._search_entry.connect("key-press-event", self._on_search_key)
        search_box.pack_start(self._search_entry, True, True, 0)

        self._search_label = Gtk.Label(label="")
        self._search_label.set_halign(Gtk.Align.START)
        search_box.pack_start(self._search_label, False, False, 6)

        self._search_case_btn = Gtk.ToggleButton(label="Aa")
        self._search_case_btn.set_tooltip_text("Match case")
        self._search_case_btn.connect("clicked", lambda b: self._do_search())
        search_box.pack_start(self._search_case_btn, False, False, 0)

        self._search_regex_btn = Gtk.ToggleButton(label=".*")
        self._search_regex_btn.set_tooltip_text("Regular expression")
        self._search_regex_btn.connect("clicked", lambda b: self._do_search())
        search_box.pack_start(self._search_regex_btn, False, False, 0)

        self._vte.connect("child-exited", self._on_child_exited)
        self._vte.connect("selection-changed", self._on_selection_changed)
        self._vte.connect("button-press-event", self._on_button_press)
        self._vte.connect("key-press-event", self._on_key_press)
        self._vte.connect("window-title-changed", self._on_title_changed)
        self._vte.add_events(Gdk.EventMask.SCROLL_MASK)

        url_regex = Vte.Regex.new_for_match(
            r'(https?://|ssh://|ftp://|git@|www\.)[\w\.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
            -1, Vte.REGEX_FLAGS_DEFAULT | 0x400)
        self._url_tag = self._vte.match_add_regex(url_regex, 0)
        self._vte.match_set_cursor_type(self._url_tag, Gdk.CursorType.HAND2)
        self._vte.set_allow_hyperlink(True)

        self._input_shadow = ""
        self._shadow_anchor = None
        self._ai_mode = False
        self._ai_client = None
        self._ai_input = ""
        self._ai_busy = False
        self._ai_generation = 0
        self._ai_cancel_event = None
        self._ai_thread = None
        self._history_search_mode = False
        self._history_search_query = ""
        self._history_search_index = 0
        self._history_search_results = []
        self._history_list_display = False
        self._history_list_results = []
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._history_sql_mode = False
        self._history_tab_mode = False
        self._history_tab_original = ""
        self._tab_fallback_pending_before = None
        self._tab_fallback_pending_time = 0
        self._connect_provider = None
        self._connect_model = None
        self._connect_key = ""
        self._connect_url = ""
        self._provider_list = []
        self._model_list = []
        self._history_show_results = []
        self._async_pending = False
        self._async_generation = 0
        self._provider_worker = None
        self._model_worker = None

        self._comando_corrente = ""
        self._pid = -1
        self._pty_fd = -1
        self._osc133_stats = ""
        self._remote_stats_cache = ""
        self._remote_stats_ts = -1000.0
        self._remote_stats_running = False

        self._osc133_markers = []
        self._osc133_rfd = -1
        self._osc133_fifo_path = ""
        self._osc133_source_id = 0
        self._osc133_buf = b""
        self._osc133_last_exit = 0
        self._osc133_cmd_start_row = -1
        self._osc133_timer_pending = False
        self._osc133_pending_lines = []
        self._osc133_integration_active = False
        self._osc133_last_history_id = None

        self._search_results = []
        self._search_index = 0
        self._search_tags = []
        self._quickmarks = []
        self._quickmark_index = -1
        self._bell_notify_cmd_running = False

        self._hints_active = False
        self._hints_buffer = ""
        self._hints_map = {}

        self._vi_copy_active = False
        self._vi_visual_active = False
        self._vi_selection_start = -1
        self._vi_selection_end = -1
        self._vi_last_key = None
        self._vi_last_key_time = 0

        self._undercurl_provider = Gtk.CssProvider()
        ctx = self._vte.get_style_context()
        ctx.add_provider(self._undercurl_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._cached_backspace_binding = self._settings.get("backspace_binding", "ascii-del")
        self._cached_delete_binding = self._settings.get("delete_binding", "escape-sequence")
        self._cached_broadcast_input = self._settings.get("broadcast_input", False)

        self._settings.connect(self.apply_settings)

        self._cmd_bar_visible = False

        self.show_all()

    def _apply_font(self):
        family = self._settings.get("font_name", "Monospace")
        size = self._settings.get("font_size", 12)
        fd = Pango.FontDescription(f"{family} {size}")
        self._vte.set_font(fd)

    def _apply_padding(self):
        h = self._settings.get("window_padding_horizontal", 2)
        v = self._settings.get("window_padding_vertical", 2)
        self._vte.set_margin_start(h)
        self._vte.set_margin_end(h)
        self._vte.set_margin_top(v)
        self._vte.set_margin_bottom(v)

    def _apply_undercurl(self):
        style = self._settings.get("undercurl_style", "single")
        css_map = {
            "single": "vte-terminal { text-decoration-line: underline; text-decoration-style: solid; }",
            "double": "vte-terminal { text-decoration-line: underline; text-decoration-style: double; }",
            "curly": "vte-terminal { text-decoration-line: underline; text-decoration-style: wavy; }",
            "dashed": "vte-terminal { text-decoration-line: underline; text-decoration-style: dashed; }",
            "dotted": "vte-terminal { text-decoration-line: underline; text-decoration-style: dotted; }",
        }
        css = css_map.get(style, css_map["single"])
        self._undercurl_provider.load_from_data(css.encode())

    def _bg_rgba(self):
        # VTE renders its own background opaque by default regardless of the
        # window's compositor opacity (it hints itself as an opaque region for
        # performance), so real "transparent terminal" requires feeding VTE's
        # own background color a reduced alpha instead.
        bg = _hex_to_gdk(self._settings.get_bg_color())
        if self._settings.get("enable_transparency", False):
            bg.alpha = max(0.0, min(1.0, self._settings.get("opacity", 1.0)))
        return bg

    def _apply_colors(self):
        fg = _hex_to_gdk(self._settings.get_fg_color())
        bg = self._bg_rgba()
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
        bg = self._bg_rgba()
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
        self._apply_padding()
        self._apply_undercurl()
        self._vte.set_scrollback_lines(self._settings.get("scrollback_lines", 10000))
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
        self._cached_backspace_binding = self._settings.get("backspace_binding", "ascii-del")
        self._cached_delete_binding = self._settings.get("delete_binding", "escape-sequence")
        self._cached_broadcast_input = self._settings.get("broadcast_input", False)

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

    def launch(self, cwd=None, command=None):
        if command:
            argv = list(command)
        else:
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
            fifo_path = os.path.join(
                os.path.expanduser("~"), ".config", "tpgk",
                f"osc133_{os.getpid()}_{id(self)}.fifo")
            try:
                os.unlink(fifo_path)
            except OSError:
                pass
            os.mkfifo(fifo_path, 0o600)
            os.chmod(fifo_path, 0o600)
            self._osc133_fifo_path = fifo_path
            env["TPGK_OSC133_FIFO"] = fifo_path
            self._osc133_rfd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)

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

if [ -n "$TPGK_OSC133_FIFO" ] && [ -p "$TPGK_OSC133_FIFO" ]; then
    exec 3>>"$TPGK_OSC133_FIFO"
fi

__TPGK_OSC133_READY=0

__tpgk_osc133_notify() {
    [ -n "$TPGK_OSC133_FIFO" ] && printf '%s\n' "$1" >&3 2>/dev/null
    return 0
}

__tpgk_osc133_stats() {
    [ -n "$TPGK_OSC133_FIFO" ] || return 0
    local load cpu mem_used mem_total disk_used disk_total
    load=$(cat /proc/loadavg 2>/dev/null)
    [ -n "$load" ] || return 0
    mem_used=$(awk '/^MemTotal/{t=$2}/^MemAvailable/{a=$2}END{printf "%d",(t-a)*1024}' /proc/meminfo 2>/dev/null)
    mem_total=$(awk '/^MemTotal/{printf "%d",$2*1024; exit}' /proc/meminfo 2>/dev/null)
    disk_used=$(df -B1 / 2>/dev/null | awk 'NR==2{printf "%d",$3}')
    disk_total=$(df -B1 / 2>/dev/null | awk 'NR==2{printf "%d",$2}')
    printf 'S%s|%s|%s|%s|%s\n' "$load" "$mem_used" "$mem_total" "$disk_used" "$disk_total" >&3 2>/dev/null
}

__tpgk_osc133_preexec() {
    [ "$__TPGK_OSC133_READY" = "1" ] || return
    case "$BASH_COMMAND" in
        __tpgk_osc133_*) return ;;
    esac
    __TPGK_OSC133_READY=0
    printf '\033]133;C\007'
    __tpgk_osc133_notify "C${BASH_COMMAND//$'\n'/ }"
}
__tpgk_osc133_precmd() {
    local _exit=$?
    __TPGK_OSC133_READY=1
    printf '\033]133;D;%s\007' "$_exit"
    __tpgk_osc133_notify "D$_exit"
    printf '\033]133;A\007'
    __tpgk_osc133_notify A
    printf '\033]7;%s\007' "file://$PWD"
    __tpgk_osc133_stats
}

# Enable SSH ControlMaster so TPGK can show live remote system stats.
# The shared socket lets a background "ssh -S ..." call reuse
# authentication established by the interactive session.
__tpgk_ssh() {
    command ssh -o ControlMaster=auto -o "ControlPath=/tmp/tpgk-ssh-$$" "$@"
}

if [ -n "$BASH_VERSION" ]; then
    alias ssh='__tpgk_ssh'
    trap '__tpgk_osc133_preexec' DEBUG
    # PROMPT_COMMAND may be an array (bash >= 5.1 - the default on distros
    # that chain their own prompt hooks, e.g. systemd/VTE integration
    # scripts under /etc/profile.d). Overwriting it as a plain string here
    # silently dropped every hook but its first array element - which then
    # also got misidentified as "the next command about to run", resetting
    # our ready flag before the user's actual command was ever read, so
    # command history capture never fired at all. Appending ourselves as
    # the *last* hook instead means every earlier hook still runs first
    # (while the ready flag is 0, so it's correctly ignored), and the flag
    # only flips to 1 once they've all finished, right before bash reads
    # the next real command.
    if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
        PROMPT_COMMAND+=(__tpgk_osc133_precmd)
    else
        PROMPT_COMMAND="${PROMPT_COMMAND}${PROMPT_COMMAND:+;}__tpgk_osc133_precmd"
    fi
    printf '\033]133;A\007'
    __tpgk_osc133_notify A
    printf '\033]7;%s\007' "file://$PWD"
elif [ -n "$ZSH_VERSION" ]; then
    autoload -Uz add-zsh-hook
    __tpgk_zsh_preexec() {
        printf '\033]133;C\007'
        __tpgk_osc133_notify "C${1//$'\n'/ }"
    }
    __tpgk_zsh_precmd() {
        local _exit=$?
        printf '\033]133;D;%s\007' "$_exit"
        __tpgk_osc133_notify "D$_exit"
        printf '\033]133;A\007'
        __tpgk_osc133_notify A
        printf '\033]7;%s\007' "file://$PWD"
        __tpgk_osc133_stats
    }
    add-zsh-hook preexec __tpgk_zsh_preexec
    add-zsh-hook precmd __tpgk_zsh_precmd
    alias ssh='__tpgk_ssh'
    printf '\033]133;A\007'
    __tpgk_osc133_notify A
    printf '\033]7;%s\007' "file://$PWD"
fi
'''
        os.makedirs(script_dir, exist_ok=True)
        try:
            with open(script_path, "w") as f:
                f.write(script)
            os.chmod(script_path, 0o600)
        except OSError:
            pass

    def _on_spawn_complete(self, terminal, pid, error, user_data=None):
        if error:
            logger.error("shell_spawn_failed error=%s", error.message)
            self._vte.feed(
                f"\r\n\x1b[31m[Failed to start shell: {error.message}]\x1b[0m\r\n".encode()
            )
        else:
            self._pid = int(pid)
            try:
                self._pty_fd = terminal.get_pty().get_fd()
            except Exception:
                self._pty_fd = -1
            if getattr(self, '_osc133_rfd', -1) >= 0:
                self._osc133_source_id = GLib.io_add_watch(
                    self._osc133_rfd, GLib.IO_IN | GLib.IO_HUP,
                    self._on_osc133_pipe_data)

    def terminate(self):
        self._cancel_ai_stream()
        if self._osc133_rfd >= 0:
            try:
                os.close(self._osc133_rfd)
            except OSError:
                pass
            self._osc133_rfd = -1
        if self._osc133_fifo_path:
            try:
                os.unlink(self._osc133_fifo_path)
            except OSError:
                pass
            self._osc133_fifo_path = ""
        self._settings.disconnect(self.apply_settings)
        if self._pid > 0:
            try:
                pgrp = self._get_foreground_pgrp()
                if pgrp > 0:
                    os.killpg(pgrp, 15)
                else:
                    os.kill(self._pid, 15)
            except OSError:
                pass
        gc.collect()

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
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        # Fix #8: warn before pasting multi-line content
        if text and ("\n" in text or "\r" in text) and self._settings.get("show_unsafe_paste_dialog", True):
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
        self._shadow_paste(text)
        self._vte.paste_clipboard()

    def paste_selection(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        self._shadow_paste(clipboard.wait_for_text())
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

    def is_ssh(self):
        if self._pid <= 0:
            return False
        try:
            with open(f"/proc/{self._pid}/environ", "rb") as f:
                env = f.read()
            if b"SSH_CONNECTION" in env or b"SSH_TTY" in env or b"SSH_CLIENT" in env:
                return True
        except (OSError, PermissionError):
            pass
        target = self._get_ssh_target()
        return target is not None

    def is_ssh_client(self):
        return self._get_ssh_target() is not None

    def _get_ssh_target(self):
        if self._pid <= 0:
            return None
        try:
            children_path = f"/proc/{self._pid}/task/{self._pid}/children"
            with open(children_path, "r") as f:
                children = f.read().strip().split()
            for child_pid in children:
                try:
                    with open(f"/proc/{child_pid}/comm", "r") as f:
                        comm = f.read().strip()
                    if comm != "ssh":
                        continue
                    with open(f"/proc/{child_pid}/cmdline", "rb") as f:
                        raw = f.read()
                    if not raw:
                        continue
                    args = raw.split(b"\x00")
                    target = None
                    for arg in args[1:]:
                        arg_s = arg.decode("utf-8", errors="replace")
                        if not arg_s or arg_s.startswith("-"):
                            continue
                        if "@" in arg_s:
                            return arg_s
                        target = arg_s
                    return target
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            pass
        return None

    def _find_ssh_control_socket(self):
        target = self._get_ssh_target()
        if not target:
            return None
        tpgk_socket = f"/tmp/tpgk-ssh-{self._pid}"
        if os.path.exists(tpgk_socket):
            return tpgk_socket
        try:
            config_path = os.path.join(os.path.expanduser("~"), ".ssh", "config")
            ctl_path = None
            if os.path.exists(config_path):
                with open(config_path) as f:
                    content = f.read()
                import re
                m = re.search(r'controlpath\s+(.+)', content, re.IGNORECASE)
                if m:
                    ctl_path = m.group(1).strip()
            if not ctl_path:
                return None
            ctl_path = ctl_path.replace("%r", target.split("@")[0] if "@" in target else os.environ.get("USER", ""))
            ctl_path = ctl_path.replace("%h", target.split("@")[-1])
            ctl_path = ctl_path.replace("%p", "22")
            ctl_path = os.path.expanduser(ctl_path)
            if os.path.exists(ctl_path):
                return ctl_path
        except OSError:
            pass
        return None

    def get_remote_stats(self):
        import time
        target = self._get_ssh_target()
        if not target:
            return ""
        now = time.monotonic()
        if self._remote_stats_cache is not None and (now - self._remote_stats_ts) < 15.0:
            return self._remote_stats_cache if self._remote_stats_cache != "__nokeys__" else ""
        cmd = (
            "cat /proc/loadavg 2>/dev/null; "
            "awk '/^MemTotal/{t=$2}/^MemAvailable/{a=$2}"
            "END{printf \"%d %d\\n\",(t-a)*1024,t*1024}' /proc/meminfo 2>/dev/null; "
            "df -B1 / 2>/dev/null | awk 'NR==2{printf \"%d %d\\n\",$3,$2}'"
        )
        ssh_cmd = ["ssh", "-o", "ConnectTimeout=3",
                   "-o", "StrictHostKeyChecking=accept-new",
                   "-o", "PreferredAuthentications=publickey,keyboard-interactive",
                   "-o", "PasswordAuthentication=no", "-o", "BatchMode=yes",
                   target, cmd]
        ctl_socket = self._find_ssh_control_socket()
        if ctl_socket:
            ssh_cmd = ["ssh", "-S", ctl_socket, "-o", "ConnectTimeout=2",
                       "-o", "StrictHostKeyChecking=accept-new", target, cmd]
        try:
            proc = subprocess.run(
                ssh_cmd, capture_output=True, text=True, timeout=5,
                env={**os.environ, "SSH_ASKPASS": "true", "DISPLAY": ""})
            if proc.returncode != 0 or not proc.stdout.strip():
                if b"Permission denied" in proc.stderr.encode():
                    self._remote_stats_cache = "__nokeys__"
                    self._remote_stats_ts = now
                else:
                    self._remote_stats_cache = ""
                    self._remote_stats_ts = now
                return ""
            lines = proc.stdout.strip().splitlines()
            if len(lines) < 3:
                self._remote_stats_cache = ""
                self._remote_stats_ts = now
                return ""
            load_parts = lines[0].split()
            if len(load_parts) < 1:
                self._remote_stats_cache = ""
                self._remote_stats_ts = now
                return ""
            cpu = float(load_parts[0]) * 100
            mem_parts = lines[1].split()
            if len(mem_parts) < 2:
                self._remote_stats_cache = ""
                self._remote_stats_ts = now
                return ""
            mem_used = int(mem_parts[0])
            mem_total = int(mem_parts[1])
            disk_parts = lines[2].split()
            if len(disk_parts) < 2:
                self._remote_stats_cache = ""
                self._remote_stats_ts = now
                return ""
            disk_used = int(disk_parts[0])
            disk_total = int(disk_parts[1])
        except (ValueError, subprocess.TimeoutExpired, OSError):
            self._remote_stats_cache = ""
            self._remote_stats_ts = now
            return ""
        mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0
        disk_pct = (disk_used / disk_total * 100) if disk_total > 0 else 0
        result = (
            f"  [SSH] CPU {cpu:5.1f}%  "
            f"RAM {self._format_bytes(mem_used)}/{self._format_bytes(mem_total)} ({mem_pct:.0f}%)  "
            f"Disk {self._format_bytes(disk_used)}/{self._format_bytes(disk_total)} ({disk_pct:.0f}%)"
        )
        self._remote_stats_cache = result
        self._remote_stats_ts = now
        return result

    def _is_echo_on(self):
        if self._pty_fd < 0:
            return True
        try:
            attr = termios.tcgetattr(self._pty_fd)
            return bool(attr[3] & termios.ECHO)
        except (termios.error, OSError):
            return True

    def _is_canonical_mode(self):
        if self._pty_fd < 0:
            return True
        try:
            attr = termios.tcgetattr(self._pty_fd)
            return bool(attr[3] & termios.ICANON)
        except (termios.error, OSError):
            return True

    def get_osc133_stats(self):
        """Return formatted stats from OSC shell integration, or empty string."""
        raw = self._osc133_stats
        if not raw:
            return ""
        try:
            parts = raw.split("|")
            if len(parts) < 5:
                return ""
            load = parts[0].split()
            mem_used = int(parts[1])
            mem_total = int(parts[2])
            disk_used = int(parts[3])
            disk_total = int(parts[4])
        except (ValueError, IndexError):
            return ""

        cpu = float(load[0]) * 100 if len(load) >= 1 else 0.0
        mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0
        disk_pct = (disk_used / disk_total * 100) if disk_total > 0 else 0
        mem_used_s = self._format_bytes(mem_used)
        mem_total_s = self._format_bytes(mem_total)
        disk_used_s = self._format_bytes(disk_used)
        disk_total_s = self._format_bytes(disk_total)

        return (
            f"  CPU {cpu:5.1f}%  "
            f"RAM {mem_used_s}/{mem_total_s} ({mem_pct:.0f}%)  "
            f"Disk {disk_used_s}/{disk_total_s} ({disk_pct:.0f}%)"
        )

    @staticmethod
    def _format_bytes(val: int) -> str:
        gb = 1024 * 1024 * 1024
        mb = 1024 * 1024
        if val >= gb:
            return f"{val / gb:.1f}G"
        return f"{val / mb:.0f}M"

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
        broadcast = getattr(self, '_cached_broadcast_input', False) or self._settings.get("broadcast_input", False)
        if broadcast:
            self._broadcast_to_others(data)

    def _broadcast_to_others(self, data_bytes):
        win = self._window
        if not hasattr(win, '_notebook'):
            return
        for nb in (win._notebook, win._notebook2):
            for i in range(nb.get_n_pages()):
                page = nb.get_nth_page(i)
                if page is not self and hasattr(page, '_vte'):
                    try:
                        page._vte.feed_child(data_bytes)
                    except Exception:
                        pass

    def feed_display(self, text: str):
        """Write display-only text to the terminal screen (never to the shell stdin)."""
        self._vte.feed(text.replace("\n", "\r\n").encode("utf-8"))

    def _scroll_to_bottom(self):
        if self._settings.get("scroll_on_keystroke", True):
            pass

    def _on_vadj_value_changed(self, adj):
        self._osc133_margin.queue_draw()
        bottom = max(0.0, adj.get_upper() - adj.get_page_size())
        self._scroll_follow = adj.get_value() >= bottom - 0.5

    def _on_vadj_changed(self, adj):
        self._osc133_margin.queue_draw()
        if not self._settings.get("scroll_on_output", True):
            return
        if not getattr(self, "_scroll_follow", True):
            return
        bottom = max(0.0, adj.get_upper() - adj.get_page_size())
        if adj.get_value() != bottom:
            adj.set_value(bottom)

    def _on_osc133_pipe_data(self, source, condition):
        try:
            data = os.read(self._osc133_rfd, 4096)
        except (OSError, BlockingIOError):
            data = b""
        if data:
            self._osc133_buf += data
            while b"\n" in self._osc133_buf:
                line, self._osc133_buf = self._osc133_buf.split(b"\n", 1)
                self._process_osc133_line(line.decode("utf-8", errors="replace").strip())
        if condition & GLib.IO_HUP:
            self._osc133_source_id = 0
            return False
        return True

    def _process_osc133_line(self, line):
        if not line:
            return
        # Fix: queue every line instead of keeping only the latest one.
        # precmd emits D<exit>, A and S back-to-back on every prompt, all
        # landing in the same 30ms debounce window, so keeping a single
        # "pending line" silently dropped all but the last of them (and,
        # once C carried the actual command text, could drop history
        # entries for fast-finishing commands).
        self._osc133_pending_lines.append(line)
        if not self._osc133_timer_pending:
            self._osc133_timer_pending = True
            def _run():
                self._osc133_timer_pending = False
                lines, self._osc133_pending_lines = self._osc133_pending_lines, []
                for pending in lines:
                    self._osc133_handle_event(pending)
                return False
            GLib.timeout_add(30, _run)

    def _osc133_handle_event(self, line):
        if not self._pid or self._pid <= 0:
            return

        # Any event proves the shell integration script is actually loaded
        # and running (as opposed to just enabled in settings), which is
        # what lets us trust "C" as the ground truth for command history
        # instead of guessing from mirrored keystrokes.
        self._osc133_integration_active = True

        try:
            col, row = self._vte.get_cursor_position()
        except Exception:
            return

        cmd = line[0] if line else ""
        if cmd == "C":
            self._osc133_cmd_start_row = row
            self._osc133_markers.append((row, "cmd_start", 0))
            self._bell_notify_cmd_running = True
            command_text = line[1:].strip()
            self._osc133_last_history_id = None
            if (command_text and not self._is_tpgk_command(command_text)
                    and self._settings.get("history_enabled", True)):
                self._osc133_last_history_id = self._history.add(command_text, self.get_cwd())
                self._input_shadow = ""

        elif cmd == "D":
            try:
                self._osc133_last_exit = int(line[1:])
            except ValueError:
                self._osc133_last_exit = 0
            if self._osc133_last_history_id is not None:
                self._history.set_exit_code(self._osc133_last_history_id, self._osc133_last_exit)
                self._osc133_last_history_id = None
            if self._bell_notify_cmd_running:
                self._bell_notify_cmd_running = False
                self._trigger_bell_notification(self._osc133_last_exit)

        elif cmd == "A":
            if row > 0:
                self._osc133_cmd_start_row = -1
                self._osc133_markers.append((row, "prompt", self._osc133_last_exit))
                if len(self._osc133_markers) > 1000:
                    self._osc133_markers = self._osc133_markers[-1000:]
                self._update_margin_visibility()

        elif cmd == "S":
            self._osc133_stats = line[1:]

    def _update_margin_visibility(self):
        if self._osc133_markers:
            self._osc133_margin.set_visible(True)
        self._osc133_margin.queue_draw()

    def _draw_osc133_margin(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        if width < 2:
            return

        # Match the terminal background so unmarked rows blend in instead of
        # showing the widget's default (light-themed) background.
        bg = _hex_to_gdk(self._settings.get_bg_color())
        cr.set_source_rgba(bg.red, bg.green, bg.blue, 1.0)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if not self._osc133_markers:
            return

        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return
        top = vadj.get_value()
        page = vadj.get_page_size()
        if page <= 0:
            return

        char_height = height / page

        for row, mtype, exit_code in self._osc133_markers:
            if mtype != "prompt":
                continue
            rel_row = row - top
            if rel_row < -1 or rel_row > page:
                continue
            y = rel_row * char_height
            if exit_code == 0:
                cr.set_source_rgba(0.2, 0.75, 0.2, 0.7)
            else:
                cr.set_source_rgba(0.85, 0.25, 0.25, 0.7)
            cr.rectangle(1, y, width - 2, char_height)
            cr.fill()

    def _scroll_to_osc133_prompt(self, direction_up):
        if not self._osc133_markers:
            return

        try:
            _cur_col, cur_row = self._vte.get_cursor_position()
        except Exception:
            cur_row = 0

        prompts = [(r, e) for r, t, e in self._osc133_markers if t == "prompt"]
        if not prompts:
            return

        target = None
        if direction_up:
            for r, _exit_code in reversed(prompts):
                if r < cur_row - 1:
                    target = r
                    break
        else:
            for r, _exit_code in prompts:
                if r > cur_row:
                    target = r
                    break

        if target is None:
            return

        vadj = self._scroll.get_vadjustment()
        vadj.set_value(target)

    def _get_command_output_range(self):
        try:
            _cur_col, cur_row = self._vte.get_cursor_position()
        except Exception:
            return None, None

        cmd_start = None
        prompt_end = None

        for row, mtype, _exit_code in self._osc133_markers:
            if mtype == "prompt" and row <= cur_row:
                prompt_end = row
            if mtype == "cmd_start" and row <= cur_row:
                cmd_start = row

        if cmd_start is not None and prompt_end is not None and cmd_start < prompt_end:
            return cmd_start, prompt_end
        return None, None

    def _copy_command_output(self):
        start_row, end_row = self._get_command_output_range()
        if start_row is None:
            return

        end_row = min(end_row, start_row + 500)

        text, _ = self._vte.get_text_range_format(
            Vte.Format.TEXT, start_row, 0, end_row, 0)
        if text:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)
            self._vte.feed(
                "\r\n\x1b[32m+ Output copied to clipboard\x1b[0m\r\n".encode()
            )
            self._vte.feed_child(b'\r')

    # ── Callbacks ──────────────────────────────────────────────

    def _on_child_exited(self, terminal, status):
        self._pid = -1
        if self._osc133_source_id > 0:
            GLib.source_remove(self._osc133_source_id)
            self._osc133_source_id = 0
        if self._osc133_rfd >= 0:
            try:
                os.close(self._osc133_rfd)
            except OSError:
                pass
            self._osc133_rfd = -1
        if getattr(self, '_osc133_fifo_path', None):
            try:
                os.unlink(self._osc133_fifo_path)
            except OSError:
                pass
        try:
            code = os.waitstatus_to_exitcode(status)
        except (AttributeError, ValueError):
            code = status >> 8
        self._vte.feed(f"\r\n\x1b[33m[Process exited with code {code}]\x1b[0m\r\n".encode("utf-8"))
        GLib.idle_add(lambda t=self: self._window.close_tab_signal(t))

    def _on_selection_changed(self, terminal):
        if self._settings.get("auto_copy_selection", True) and terminal.get_has_selection():
            terminal.copy_clipboard_format(Vte.Format.TEXT)

    def _get_visible_text(self, num_lines):
        try:
            _, end_row = self._vte.get_cursor_position()
            start_row = max(0, end_row - num_lines)
            text, _ = self._vte.get_text_range_format(
                Vte.Format.TEXT, start_row, 0, end_row, -1)
            return text or ""
        except Exception:
            text = self._vte.get_text_format(Vte.Format.TEXT) or ""
            lines = text.split("\n")
            if len(lines) > num_lines:
                lines = lines[-num_lines:]
            return "\n".join(lines)

    def _on_button_press(self, terminal, event):
        if event.button == 2:
            # Middle-click paste is normally handled entirely inside VTE's
            # default handler, bypassing our code (and _input_shadow) as a
            # result. Do it ourselves so the pasted text lands in history.
            self.paste_selection()
            return True
        if event.button != 1 and event.button != 3:
            return False
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if event.button == 3:
            self._show_context_menu(event)
            return True
        url = self._url_at_position(int(event.x), int(event.y))
        if not url:
            url = self._url_from_text_at(int(event.x), int(event.y))
        if url and ctrl:
            self._open_url(url)
            return True
        return False

    _URL_RE = re.compile(
        r'(https?://|ssh://|ftp://|git@|www\.)[\w\.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
        re.IGNORECASE)

    def _pixel_to_cell(self, x, y):
        cw = self._vte.get_char_width()
        ch = self._vte.get_char_height()
        if cw <= 0 or ch <= 0:
            return (0, 0)
        padding = self._settings.get("window_padding_horizontal", 2)
        col = max(0, (x - padding - 8) // cw)
        row = y // ch
        return (col, row)

    def _url_at_position(self, x, y):
        col, row = self._pixel_to_cell(x, y)
        result = self._vte.match_check(col, row)
        if result is None or result[0] is None:
            return None
        matched_text = result[0]
        if matched_text:
            if matched_text.startswith("www.") and not matched_text.startswith("http"):
                matched_text = "http://" + matched_text
            return matched_text
        return None

    def _url_from_text_at(self, x, y):
        col, row = self._pixel_to_cell(x, y)
        try:
            text, _ = self._vte.get_text_range_format(
                Vte.Format.TEXT, row, 0, row, -1)
        except Exception:
            return None
        if not text:
            return None
        line = text.rstrip("\n")
        for m in self._URL_RE.finditer(line):
            if m.start() <= col <= m.end():
                url = m.group(0)
                if url.startswith("www.") and not url.startswith("http"):
                    url = "http://" + url
                return url
        return None

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

        if self._osc133_markers:
            menu.append(Gtk.SeparatorMenuItem())
            copy_out_item = Gtk.MenuItem(label="Copy Command Output")
            copy_out_item.set_tooltip_text(
                "Copy the output of the last command to the clipboard")
            copy_out_item.connect("activate", lambda _: self._copy_command_output())
            menu.append(copy_out_item)

        url = self._url_at_position(int(event.x), int(event.y))
        if not url:
            url = self._url_from_text_at(int(event.x), int(event.y))
        if url:
            menu.append(Gtk.SeparatorMenuItem())
            copy_url_item = Gtk.MenuItem(label=f"Copy URL: {url[:60]}{'...' if len(url) > 60 else ''}")
            copy_url_item.set_tooltip_text("Copy this URL to the clipboard")
            copy_url_item.connect("activate", lambda _: self._copy_url(url))
            menu.append(copy_url_item)

            open_url_item = Gtk.MenuItem(label="Open URL")
            open_url_item.connect("activate", lambda _: self._open_url(url))
            menu.append(open_url_item)

        menu.append(Gtk.SeparatorMenuItem())

        fm_item = Gtk.MenuItem(label="Open File Manager Here")
        fm_item.connect("activate", lambda _: self._open_fm())
        menu.append(fm_item)

        menu.append(Gtk.SeparatorMenuItem())

        sel_all_item = Gtk.MenuItem(label="Select All")
        sel_all_item.connect("activate", lambda _: self.select_all())
        menu.append(sel_all_item)

        menu.append(Gtk.SeparatorMenuItem())

        srch_item = Gtk.MenuItem(label="Search Scrollback...")
        srch_item.set_tooltip_text("Search in the scrollback buffer (Ctrl+Shift+F)")
        srch_item.connect("activate", lambda _: self._show_search())
        menu.append(srch_item)

        qm_item = Gtk.MenuItem(label="Set Quickmark")
        qm_item.set_tooltip_text("Bookmark this position (Ctrl+Shift+M)")
        qm_item.connect("activate", lambda _: self._set_quickmark())
        menu.append(qm_item)

        if self._quickmarks:
            clear_qm_item = Gtk.MenuItem(label=f"Clear All Quickmarks ({len(self._quickmarks)})")
            clear_qm_item.connect("activate", lambda _: self._remove_all_quickmarks())
            menu.append(clear_qm_item)

        menu.append(Gtk.SeparatorMenuItem())

        broadcast_on = self._settings.get("broadcast_input", False)
        cast_item = Gtk.CheckMenuItem(label="Broadcast Input")
        cast_item.set_active(broadcast_on)
        cast_item.connect("activate",
                          lambda b: self._settings.set("broadcast_input", b.get_active()))
        menu.append(cast_item)

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

    def _shadow_paste(self, text):
        # Pasted text (clipboard or primary selection) goes straight to the
        # pty via VTE and never passes through _on_key_press, so without this
        # the shadow buffer silently diverges from what was actually typed
        # and history records a mangled command (e.g. a pasted port number
        # missing from "ssh -p <pasted> host").
        if not text:
            return
        if not self._input_shadow and self._shadow_anchor is None:
            # Paste can be the very first action on a fresh line (e.g.
            # middle-click before typing anything), which never touches
            # _on_key_press, so the anchor capture there never ran.
            try:
                self._shadow_anchor = self._vte.get_cursor_position()
            except Exception:
                self._shadow_anchor = None
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = normalized.split('\n')
        self._input_shadow += lines[0]
        if len(lines) > 1:
            for line in [self._input_shadow] + lines[1:-1]:
                cmd = line.strip()
                if cmd and not self._is_tpgk_command(cmd) and self._settings.get("history_enabled", True):
                    self._history.add(cmd, self.get_cwd())
            self._input_shadow = lines[-1]

    def _get_real_command_text(self):
        # Reads the command line straight off the terminal screen, from the
        # cursor position captured right after the shell's prompt up to
        # where the cursor is now, instead of trusting the keystroke-mirrored
        # _input_shadow. This is what makes history correct even without
        # OSC 133 shell integration: it reflects whatever the shell's own
        # line editor put there, including Up/Down history recall, native
        # tab completion, or mid-line edits with the arrow keys - none of
        # which _input_shadow can see since they don't append plain text.
        if self._shadow_anchor is None:
            return self._input_shadow.strip()
        try:
            start_col, start_row = self._shadow_anchor
            end_col, end_row = self._vte.get_cursor_position()
            text, _ = self._vte.get_text_range_format(
                Vte.Format.TEXT, start_row, start_col, end_row, end_col)
        except Exception:
            return self._input_shadow.strip()
        if not text:
            return self._input_shadow.strip()
        return text.strip()

    def _on_key_press(self, terminal, event):
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(state & Gdk.ModifierType.MOD1_MASK)
        key = event.keyval

        if (not self._input_shadow and self._shadow_anchor is None
                and not self._ai_mode and not self._cmd_bar_visible
                and not self._history_search_mode and not self._async_pending
                and not self._provider_list and not self._model_list
                and not self._hints_active and not self._vi_copy_active):
            try:
                self._shadow_anchor = self._vte.get_cursor_position()
            except Exception:
                self._shadow_anchor = None
            # The very first keystroke of a fresh command line (whatever it
            # is - a printable char, an Up arrow to recall shell history, a
            # paste) finds the cursor sitting right after the shell's own
            # prompt. Anchoring on it here lets _get_real_command_text() read
            # the actual rendered line at Enter time instead of relying
            # solely on mirrored keystrokes, which miss anything the shell's
            # own line editor does on its own (history recall, completion).
            try:
                self._shadow_anchor = self._vte.get_cursor_position()
            except Exception:
                self._shadow_anchor = None

        if ctrl and shift:
            if self._hints_active:
                if key == Gdk.KEY_H or key == Gdk.KEY_h:
                    self._deactivate_hints()
                    return True
                return True
            if self._vi_copy_active:
                if key == Gdk.KEY_Y or key == Gdk.KEY_y:
                    self._deactivate_vi_copy()
                    return True
                return True
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
            if key == Gdk.KEY_Up:
                self._scroll_to_osc133_prompt(direction_up=True)
                return True
            if key == Gdk.KEY_Down:
                self._scroll_to_osc133_prompt(direction_up=False)
                return True
            if key == Gdk.KEY_F or key == Gdk.KEY_f:
                self._show_search()
                return True
            if key == Gdk.KEY_M or key == Gdk.KEY_m:
                self._set_quickmark()
                return True
            if key == Gdk.KEY_B or key == Gdk.KEY_b:
                current = self._settings.get("broadcast_input", False)
                self._settings.set("broadcast_input", not current)
                self._vte.feed(
                    f"\r\n\x1b[33mBroadcast input: {'ON' if not current else 'OFF'}\x1b[0m\r\n".encode()
                )
                return True
            if key == Gdk.KEY_P or key == Gdk.KEY_p:
                self._show_command_bar()
                return True
            if key == Gdk.KEY_H or key == Gdk.KEY_h:
                if self._settings.get("hint_mode_enabled", True):
                    self._activate_hints()
                return True
            if key == Gdk.KEY_Y or key == Gdk.KEY_y:
                if self._settings.get("vi_copy_mode_enabled", False):
                    self._activate_vi_copy()
                return True

        if self._hints_active:
            self._handle_hint_key(event)
            return True

        if self._vi_copy_active:
            self._handle_vi_copy_key(event)
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
                self._exit_history_search_mode()
                return True
            if key == Gdk.KEY_W or key == Gdk.KEY_w:
                self.feed_command_bytes(b'\x17')
                parts = self._input_shadow.rsplit(' ', 1)
                self._input_shadow = parts[0] if len(parts) > 1 else ""
                return True
            if key == Gdk.KEY_C or key == Gdk.KEY_c:
                real_text = self._get_real_command_text()
                if real_text and not self._is_tpgk_command(real_text) and self._settings.get("history_enabled", True):
                    self._history.add(real_text, self.get_cwd())
                self.feed_command_bytes(b'\x03')
                self._input_shadow = ""
                self._shadow_anchor = None
                self._ai_mode = False
                self._ai_generation += 1
                self._ai_busy = False
                self._cancel_ai_stream(invalidate=False)
                self._provider_list = []
                self._model_list = []
                self._async_pending = False
                self._exit_history_search_mode()
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
            if key == Gdk.KEY_M or key == Gdk.KEY_m:
                self._jump_next_quickmark()
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
                self._cancel_ai_stream()
                self._ai_input = ""
                self.feed_command_bytes(b'\x15')
                self._vte.feed(b'\r\n')
                self._exit_history_search_mode()
                return True
            if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                question = self._ai_input.strip()
                self._ai_input = ""
                if question == "/ai off":
                    self._ai_mode = False
                    self._cancel_ai_stream()
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
            # Any other key means the user has moved on to typing something
            # else. Silently drop the pending AI check instead of eating the
            # keystroke (previously every character typed while a /connect
            # check was still in flight was discarded with no feedback,
            # corrupting whatever command the user typed next).
            self._async_generation += 1
            self._async_pending = False

        if self._provider_list or self._model_list or self._history_show_results:
            text = event.string
            if key == Gdk.KEY_Escape:
                self._provider_list = []
                self._model_list = []
                self._history_show_results = []
                self._async_pending = False
                self._vte.feed(b"\r\n\x1b[37mSelection cancelled.\x1b[0m\r\n")
                self._input_shadow = ""
                self._exit_history_search_mode()
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
            # Not a selection digit either: the user has moved on to typing
            # something else. Clear the pending menu but let the keystroke
            # fall through to normal handling instead of discarding it.
            self._provider_list = []
            self._model_list = []
            self._history_show_results = []

        if key == Gdk.KEY_Tab and self._input_shadow.startswith('/'):
            self._autocomplete_tpgk()
            return True

        if key == Gdk.KEY_Tab:
            # Bash completion for `ssh ` can synchronously inspect hosts and
            # block readline for several seconds. When TPGK already has SSH
            # history, prefer it so Escape can always return immediately.
            if (self._input_shadow.endswith(" ")
                    and self._input_shadow.rstrip() == "ssh"
                    and self._history.search("ssh", 1, self.get_cwd())):
                self._start_history_tab_complete(allow_list=True)
                return True
            # Let the shell's own completion run first on single Tab. A
            # second Tab shortly after, with nothing typed in between (the
            # shadow is unchanged apart from Tab characters), triggers
            # history instead. Using a time window rather than requiring the
            # very next key event to be Tab makes this robust to an
            # incidental stray key (e.g. a modifier tap) landing between the
            # two presses, which would otherwise silently fall back to
            # single-Tab behavior on the second press.
            if self._input_shadow.strip():
                now = GLib.get_monotonic_time()
                if (self._tab_fallback_pending_before is not None
                        and now - self._tab_fallback_pending_time < 600_000
                        and self._input_shadow.rstrip('\t') == self._tab_fallback_pending_before):
                    self._tab_fallback_pending_before = None
                    self._start_history_tab_complete(allow_list=True)
                    return True
                else:
                    self._tab_fallback_pending_before = self._input_shadow
                    self._tab_fallback_pending_time = now
            self._input_shadow += "\t"
            return False

        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            shadow = self._input_shadow.strip()
            if not self._is_tpgk_command(shadow):
                # The mirrored buffer misses anything the shell's own line
                # editor put there instead of individual keystrokes (native
                # Up/Down history recall, mid-line edits) - fall back to
                # reading the rendered line so those still get intercepted.
                real_text = self._get_real_command_text()
                if self._is_tpgk_command(real_text):
                    shadow = real_text
            if shadow:
                is_tpgk_cmd = self._is_tpgk_command(shadow)
                # TPGK commands never reach the shell (the readline buffer
                # gets cleared below), so OSC 133 "C" never fires for them
                # and they must still be recorded here. Regular commands are
                # skipped once shell integration is confirmed active: its
                # "C" event carries the command exactly as the shell saw it
                # (unlike this mirrored buffer, which misses anything typed
                # outside individual keystrokes — pasted text, history
                # recalled with the shell's own Up/Down arrows, etc.).
                if self._settings.get("history_enabled", True):
                    if is_tpgk_cmd:
                        self._history.add(shadow, self.get_cwd())
                    elif not self._osc133_integration_active:
                        self._history.add(self._get_real_command_text(), self.get_cwd())
                self._shadow_anchor = None
                # Fix #2: clear bash readline buffer before handling a TPGK command,
                # because regular chars already landed in bash's readline buffer
                if is_tpgk_cmd:
                    self.feed_command_bytes(b'\x15')
                if shadow == "/ai off":
                    self._ai_mode = False
                    self._cancel_ai_stream()
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
                elif shadow.startswith("/history"):
                    parts = shadow.split(None, 1)
                    args = parts[1] if len(parts) > 1 else ""
                    if args.strip().lower() == "clear":
                        self._history.clear()
                        self._vte.feed(b"\r\n\x1b[32mHistory cleared.\x1b[0m\r\n")
                        self._vte.feed_child(b'\r')
                    else:
                        self._cmd_history(args)
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
                elif shadow.startswith("/learn"):
                    args = shadow.split(None, 1)[1] if " " in shadow else ""
                    self._cmd_learn(args)
                    self._vte.feed_child(b'\r')
                    self._input_shadow = ""
                    return True
                elif shadow.startswith("/optimize"):
                    args = shadow.split(None, 1)[1] if " " in shadow else ""
                    self._cmd_optimize(args)
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
            bs = getattr(self, '_cached_backspace_binding', None) or self._settings.get("backspace_binding", "ascii-del")
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
            dl = getattr(self, '_cached_delete_binding', None) or self._settings.get("delete_binding", "escape-sequence")
            if dl == "ascii-del":
                self.feed_command_bytes(b'\x7f')
            elif dl == "control-h":
                self.feed_command_bytes(b'\x08')
            else:
                self.feed_command_bytes(b'\x1b[3~')
            return True

        text = event.string
        slash_search = text == "/" or text == "?"
        if slash_search and not ctrl and not alt and not self._scroll_follow:
            if not self._input_shadow and not self._ai_mode and not self._cmd_bar_visible:
                self._show_search()
                return True
        if text and len(text) == 1 and ord(text[0]) >= 0x20:
            self._input_shadow += text

        return False

    def _on_title_changed(self, terminal):
        title = terminal.get_window_title()
        if not title:
            return
        self._window.set_tab_title_from_terminal(self, title)

    def _show_command_bar(self):
        if self._cmd_bar_visible:
            return
        self._cmd_bar_visible = True
        self._cmd_bar_revealer.set_reveal_child(True)
        self._cmd_entry.set_text("/")
        self._build_cmd_list("")
        self._cmd_entry.grab_focus()
        # GTK selects the whole entry text on focus-in (gtk-entry-select-on-focus);
        # without collapsing the selection, the first keystroke overwrites the "/".
        self._cmd_entry.select_region(-1, -1)

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
        for cmd, desc in self._CMD_COMMANDS:
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
                row.cmd_data = cmd.split()[0]
                self._cmd_list.add(row)
                if first is None:
                    first = row
        if first:
            self._cmd_list.select_row(first)

    def _on_cmd_bar_row_activated(self, listbox, row):
        if not hasattr(row, 'cmd_data'):
            return
        cmd_label = row.cmd_data
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
            # Let the entry's own "activate" signal fire (_on_cmd_bar_activated),
            # so whatever text is actually in the entry gets executed —
            # not just the highlighted suggestion, in case args were typed.
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
                sel = self._cmd_list.get_selected_row() or children[0]
                if hasattr(sel, 'cmd_data'):
                    self._cmd_entry.set_text(sel.cmd_data + " ")
                    self._cmd_entry.set_position(-1)
            return True
        return False

    def _execute_tpgk_command(self, shadow):
        self._history.add(shadow, self.get_cwd())
        self.feed_command_bytes(b'\x15')
        if shadow == "/ai off":
            self._ai_mode = False
            self._cancel_ai_stream()
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
            parts = shadow.split(None, 1)
            args = parts[1] if len(parts) > 1 else ""
            if args.strip().lower() == "clear":
                self._history.clear()
                self._vte.feed(b"\r\n\x1b[32mHistory cleared.\x1b[0m\r\n")
            else:
                self._cmd_history(args)
        elif shadow.startswith("/wnotes"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_wnotes(args)
        elif shadow.startswith("/onotes"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_onotes(args)
        elif shadow.startswith("/learn"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_learn(args)
        elif shadow.startswith("/optimize"):
            args = shadow.split(None, 1)[1] if " " in shadow else ""
            self._cmd_optimize(args)
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
        client = self._ai_client
        cancel_event = threading.Event()
        self._ai_cancel_event = cancel_event
        self._ai_thread = threading.Thread(target=self._run_ai_stream,
                                           args=(client, question, gen, cancel_event), daemon=True)
        self._ai_thread.start()

    def _cancel_ai_stream(self, invalidate=True):
        if self._ai_cancel_event is not None:
            self._ai_cancel_event.set()
        if self._ai_client is not None:
            self._ai_client.cancel()
        if self._ai_busy and invalidate:
            self._ai_generation += 1
        self._ai_busy = False
        self._ai_cancel_event = None

    def _run_ai_stream(self, client, question, gen, cancel_event):
        first_token = True
        try:
            for chunk in client.chat_stream(question, cancel_event):
                if cancel_event.is_set() or not self._ai_mode or self._ai_generation != gen:
                    break
                if first_token:
                    first_token = False
                    GLib.idle_add(lambda g=gen: (self._vte.feed(b'\r\x1b[K')
                                         if self._ai_generation == g and self._ai_mode else None))
                data = chunk.encode("utf-8")
                GLib.idle_add(
                    lambda data=data, g=gen:
                        (self._vte.feed(data)
                         if self._ai_generation == g and self._ai_mode else None))
        except Exception as error:
            if cancel_event.is_set() or isinstance(error, AIRequestCancelled):
                logger.info("ai_request_cancelled")
            else:
                logger.exception("ai_request_failed")
            if (not cancel_event.is_set() and not isinstance(error, AIRequestCancelled)
                    and self._ai_mode and self._ai_generation == gen):
                GLib.idle_add(
                    lambda err=str(error), g=gen:
                        (self._vte.feed(
                            f"\r\n\x1b[31m[AI Error] {err}\x1b[0m\r\n".encode())
                         if self._ai_generation == g else None)
                )
        GLib.idle_add(lambda g=gen: self._on_ai_finished(g) if self._ai_generation == g else None)

    def _on_ai_finished(self, gen=None):
        if gen is not None and self._ai_generation != gen:
            return
        self._ai_busy = False
        self._ai_cancel_event = None
        self._ai_thread = None
        if self._ai_mode:
            self._vte.feed(b'\r\n\r\n')

    # ── History search ────────────────────────────────────────

    def _exit_history_search_mode(self):
        was_list_display = self._history_list_display
        self._history_search_mode = False
        self._history_list_display = False
        self._history_sql_mode = False
        self._history_tab_mode = False
        self._history_search_query = ""
        self._history_search_results = []
        self._history_list_results = []
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._input_shadow = ""
        if was_list_display:
            try:
                # Leaving the alternate screen buffer restores the primary
                # screen exactly as it was *at the moment 1049h was sent* -
                # which is before bash had a chance to actually process and
                # echo back the Ctrl+U that erased "/history ..." from the
                # line (that echo is asynchronous, over the pty, and loses
                # the race against feed() switching buffers immediately).
                # So the restored screen still shows the typed command, not
                # a bare prompt. Clearing it and asking the real shell for a
                # fresh prompt (like every other tpgk command already does
                # via feed_child) sidesteps the race entirely instead of
                # trying to preserve/restore a snapshot that can't be
                # trusted to be clean.
                self._vte.feed(b'\033[?1049l\033[H\033[2J')
            except Exception:
                pass
            self._vte.feed_child(b'\r')
        return was_list_display

    def _start_history_search(self):
        self._history_search_mode = True
        self._history_search_query = ""
        self._history_search_index = -1
        self._history_search_results = self._history.interactive_search("")
        self._show_search_results()

    def _handle_history_search_key(self, event):
        key = event.keyval
        text = event.string

        if key == Gdk.KEY_Escape or key == 0xff1b or key == 0x1b:
            # Tab-triggered browsing started from a command already being
            # typed (not a "/history" command line) - the shell buffer was
            # cleared to show the full-screen list, so cancelling must retype
            # what the user had so far instead of leaving an empty prompt.
            tab_mode = self._history_tab_mode
            original = self._history_tab_original if tab_mode else ""
            # _exit_history_search_mode() already asks the real shell for a
            # fresh prompt when leaving the full-screen list view; adding
            # another \r\n here on top of that would leave a stray blank
            # line and put the cursor past the newly-drawn prompt.
            if not self._exit_history_search_mode():
                self._vte.feed(b'\r\n')
            if tab_mode and original.strip():
                self._vte.feed_child(original.encode("utf-8"))
            return True

        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            if self._history_list_display:
                results = self._history_list_results
                sel_idx = self._history_list_index
                tab_mode = self._history_tab_mode
                original = self._history_tab_original
                self._exit_history_search_mode()
                if results and 0 <= sel_idx < len(results):
                    row = results[sel_idx]
                    if len(row) >= 4:
                        cmd = row[1]
                    else:
                        cmd = str(tuple(row))
                    if tab_mode:
                        # Fill the line like a completion, don't run it - the
                        # user still gets to review/edit before hitting Enter.
                        self._input_shadow = cmd
                        self._vte.feed_child(cmd.encode("utf-8"))
                    else:
                        self._vte.feed_child((cmd + "\n").encode("utf-8"))
                        self._history.add(cmd, self.get_cwd())
                elif tab_mode and original.strip():
                    self._input_shadow = original
                    self._vte.feed_child(original.encode("utf-8"))
                else:
                    self._vte.feed(b'\r\n')
                self._history_list_results = []
                self._history_list_index = 0
                self._history_list_nlines = 0
                return True

            self._history_search_mode = False
            if self._history_search_results and self._history_search_index >= 0:
                cmd = self._history_search_results[self._history_search_index][0]
                self._vte.feed_child((cmd + "\n").encode("utf-8"))
                self._history.add(cmd, self.get_cwd())
            else:
                self._vte.feed(b'\r\n')
            self._history_search_query = ""
            self._history_search_results = []
            return True

        if self._history_list_display:
            if key == Gdk.KEY_Up:
                if self._history_list_results and self._history_list_index > 0:
                    self._history_list_index -= 1
                    self._show_history_list()
                return True

            if key == Gdk.KEY_Down:
                if self._history_list_results and self._history_list_index < len(self._history_list_results) - 1:
                    self._history_list_index += 1
                    self._show_history_list()
                return True

            if key == Gdk.KEY_BackSpace:
                if self._history_search_query:
                    self._history_search_query = self._history_search_query[:-1]
            elif text and len(text) == 1 and ord(text[0]) >= 0x20:
                self._history_search_query += text

            self._history_list_index = 0
            if not self._history_sql_mode:
                self._history_list_results = self._history.search(self._history_search_query, 50, self.get_cwd())
            self._history_search_results = [(cmd,) for _, cmd, _, _ in self._history_list_results] if self._history_list_results else []
            self._show_history_list()
            return True

        if key == Gdk.KEY_Up:
            if self._history_search_results:
                self._history_search_index = min(
                    self._history_search_index + 1,
                    len(self._history_search_results) - 1,
                )
                self._show_search_results()
            return True

        if key == Gdk.KEY_Down:
            if self._history_search_results:
                self._history_search_index = max(self._history_search_index - 1, -1)
                if self._history_search_index < 0:
                    self._vte.feed(b'\r\033[K')
                    self._vte.feed(f"\r\x1b[90m(query)> {self._history_search_query}\x1b[0m".encode())
                else:
                    self._show_search_results()
            return True

        if key == Gdk.KEY_BackSpace:
            if self._history_search_query:
                self._history_search_query = self._history_search_query[:-1]
        elif text and len(text) == 1 and ord(text[0]) >= 0x20:
            self._history_search_query += text
            self._history_search_index = -1

        self._history_search_results = self._history.interactive_search(self._history_search_query)
        self._show_search_results()
        return True

    def _show_search_results(self):
        self._vte.feed(b'\r\033[K')
        if self._history_search_index >= 0 and self._history_search_index < len(self._history_search_results):
            selected = self._history_search_results[self._history_search_index][0]
            display_sel = selected.replace('\n', '\x1b[90m\u23ce\x1b[92m ').replace('\r', '')
            self._vte.feed(f"\r\x1b[92m> {display_sel}\x1b[0m".encode())
        elif self._history_search_results:
            preview = self._history_search_results[0][0]
            display_prev = preview.replace('\n', '\x1b[90m\u23ce\x1b[33m ').replace('\r', '')
            count = len(self._history_search_results)
            self._vte.feed(
                f"\r\x1b[44m\x1b[37m(reverse-i-search)`{self._history_search_query}`: {count}\x1b[0m  \x1b[33m{display_prev[:60]}\x1b[0m".encode()
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
            enter_label = "fill" if self._history_tab_mode else "execute"
            if not self._history_sql_mode:
                out += "\x1b[90mType to filter, Esc to cancel.\x1b[0m\r\n"
            else:
                out += f"\x1b[90m\u2191\u2193 select, Enter {enter_label}, Esc cancel\x1b[0m\r\n"
            self._history_list_nlines = out.count('\n')
            self._vte.feed(f"\033[2J\033[H{out}".encode())
            return

        total = len(results)
        per_page = 10
        page_start = (self._history_list_index // per_page) * per_page
        page_end = min(total, page_start + per_page)

        out = "\x1b[36m─── History ───\x1b[0m\r\n"
        for i in range(page_start, page_end):
            row = results[i]
            if len(row) >= 4 and not self._history_sql_mode:
                _, cmd, _, ts = row
                time_str = ts[-8:] if ts else ""
                raw_cmd = str(cmd)
            elif self._history_sql_mode:
                raw_cmd = " | ".join(str(v) for v in row)
                time_str = ""
            else:
                raw_cmd = str(tuple(row))
                time_str = ""

            display_cmd = raw_cmd.replace('\n', '\x1b[90m\u23ce\x1b[0m ').replace('\r', '')
            display = display_cmd[:100] + ("..." if len(raw_cmd) > 100 else "")

            if i == self._history_list_index:
                out += f"\x1b[92m \u25b6 \x1b[0m{display}  \x1b[90m{time_str}\x1b[0m\r\n"
            else:
                out += f"  {display}  \x1b[90m{time_str}\x1b[0m\r\n"

        query_disp = f"'{self._history_search_query}'" if self._history_search_query else "all"
        enter_label = "fill" if self._history_tab_mode else "execute"
        footer = ""
        if not self._history_sql_mode:
            footer = f"\x1b[90m─── {total} matches for {query_disp} — \u2191\u2193 select, type to filter, Enter {enter_label}, Esc cancel\x1b[0m"
        else:
            footer = f"\x1b[90m─── {total} results — \u2191\u2193 select, Enter {enter_label}, Esc cancel\x1b[0m"
        out += footer
        self._history_list_nlines = out.count('\n')
        self._vte.feed(f"\033[2J\033[H{out}".encode())

    def _replay_history_number(self, num: int):
        results = self._history.interactive_search("", 20)
        if 0 <= num - 1 < len(results):
            cmd = results[num - 1][0]
            # Fix #11: \x1b[K is a display escape, meaningless as pty input; use \x15 to kill readline
            self._vte.feed_child(b'\x15')
            self._vte.feed_child(cmd.encode("utf-8"))

    def _fill_history_match(self, cmd: str):
        # Replaces the current line in-place with a single unambiguous
        # history match - same "fill" semantics Enter has in the picker,
        # just without needing to open it for a match that isn't in doubt.
        self.feed_command_bytes(b'\x15')
        self._input_shadow = cmd
        self._vte.feed_child(cmd.encode('utf-8'))

    def _start_history_tab_complete(self, allow_list=True):
        # Use the real on-screen text, not the keystroke-mirrored shadow:
        # the shadow can diverge (shell-native history recall, mid-line
        # edits, partial completions already typed) and querying history
        # with a stale/wrong string is exactly what produces irrelevant
        # results in the picker.
        query = self._get_real_command_text()
        # After shell completion output, the VTE range from shadow anchor
        # to cursor spans extra lines. Fall back to the keystroke mirror.
        if '\n' in query:
            query = self._input_shadow.rstrip('\t')
        results = self._history.search(query, 50, self.get_cwd())
        if not results:
            return
        if len(results) == 1:
            # A "certain" case: exactly one command in history matches.
            # Fill it directly - on a single Tab this is the only thing we
            # do (no popup out of nowhere); on a double Tab it's still the
            # right call, since showing a one-item list would just add an
            # extra Enter for no benefit.
            self._fill_history_match(results[0][1])
            return
        if not allow_list:
            return
        self._history_tab_mode = True
        # _input_shadow includes the Tab keystroke that triggered this view.
        # Never feed that control character back to readline on Escape.
        self._history_tab_original = self._input_shadow.rstrip("\t") or query
        self._history_list_display = True
        self._history_search_mode = True
        self._history_search_query = query
        self._history_search_index = 0
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._history_sql_mode = False
        self.feed_command_bytes(b'\x15')
        self._vte.feed(b'\033[?1049h')
        self._history_list_results = results
        self._history_search_results = (
            [(cmd,) for _, cmd, _, _ in self._history_list_results]
            if self._history_list_results else []
        )
        self._show_history_list()

    # ── TPGK commands ──────────────────────────────────────────

    def _cmd_history(self, args=""):
        self._history_list_display = True
        self._history_search_mode = True
        self._history_search_query = args.strip() if args else ""
        self._history_search_index = 0
        self._history_list_index = 0
        self._history_list_nlines = 0
        self._history_sql_mode = False
        self._vte.feed(b'\033[?1049h')
        query = self._history_search_query.strip()
        is_sql = False
        sql = query
        if query.upper().startswith(':SQL '):
            is_sql = True
            sql = query[5:].strip()
        elif query.upper().startswith(':SQL\t'):
            is_sql = True
            sql = query[5:].strip()
        elif query.upper().startswith('SELECT') or query.upper().startswith('EXPLAIN'):
            is_sql = True
        if is_sql:
            self._history_sql_mode = True
            try:
                self._history_list_results = self._history.sql_search(sql)
            except (ValueError, sqlite3.Error) as e:
                self._vte.feed(f"\033[2J\033[H\x1b[31mSQL Error: {e}\x1b[0m\r\n\x1b[90mPress Esc to exit.\x1b[0m\r\n".encode())
                self._history_list_results = []
        else:
            self._history_list_results = self._history.search(self._history_search_query, 50, self.get_cwd())
            self._history_search_results = [(cmd,) for _, cmd, _, _ in self._history_list_results] if self._history_list_results else []
            self._show_history_list()
            return
        self._history_search_results = []
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

    def _cmd_learn(self, args=""):
        # Bulk-import commands into history without executing them, e.g. for
        # cleaning up a fresh shell with no history yet. Lines are inserted
        # via HistoryManager.add() exactly like a typed command would be,
        # just with exit_code=-1 ("never run").
        MAX_LINES = 5000
        MAX_LINE_LEN = 1000
        path = args.strip()
        if not path:
            self._vte.feed(b"\r\n\x1b[33mUsage: /learn <file>\x1b[0m\r\n")
            return
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.get_cwd(), path)
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            self._vte.feed(f"\r\n\x1b[31m/learn: {e.strerror or e}\x1b[0m\r\n".encode())
            return

        cwd = self.get_cwd()
        added = 0
        skipped_long = 0
        truncated = len(lines) > MAX_LINES
        for line in lines[:MAX_LINES]:
            cmd = line.strip()
            if not cmd or cmd.startswith("#"):
                continue
            if len(cmd) > MAX_LINE_LEN:
                skipped_long += 1
                continue
            self._history.add(cmd, cwd)
            added += 1

        msg = f"\r\n\x1b[32m/learn: {added} command(s) added to history from {path}\x1b[0m\r\n"
        self._vte.feed(msg.encode())
        if skipped_long:
            self._vte.feed(
                f"\x1b[33m/learn: {skipped_long} line(s) skipped (too long, not a command)\x1b[0m\r\n".encode()
            )
        if truncated:
            self._vte.feed(
                f"\x1b[33m/learn: file has more than {MAX_LINES} lines, only the first {MAX_LINES} were read\x1b[0m\r\n".encode()
            )

    @staticmethod
    def _human_size(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
            n /= 1024
        return f"{n:.1f}TB"

    def _cmd_optimize(self, args=""):
        if args.strip().lower() != "history":
            self._vte.feed(b"\r\n\x1b[33mUsage: /optimize history\x1b[0m\r\n")
            return
        self._vte.feed(b"\r\n\x1b[90mOptimizing history database...\x1b[0m\r\n")
        stats = self._history.optimize()
        self._vte.feed(
            f"\x1b[32m/optimize: removed {stats['duplicates_removed']} duplicate(s) "
            f"({stats['rows_before']} -> {stats['rows_after']} rows)\x1b[0m\r\n".encode()
        )
        self._vte.feed(
            f"\x1b[32m/optimize: db size {self._human_size(stats['size_before'])} -> "
            f"{self._human_size(stats['size_after'])}\x1b[0m\r\n".encode()
        )

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
        gen = self._async_generation
        keys = self._settings.get("ai_keys", {})
        models = self._settings.get("ai_models", {})
        urls = self._settings.get("ai_urls", {})
        available = []

        for provider in ["openai", "claude", "gemini", "deepseek", "ollama", "custom"]:
            if gen != self._async_generation:
                return
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

        GLib.idle_add(lambda g=gen: self._on_provider_list_ready(available) if self._async_generation == g else None)

    def _on_provider_list_ready(self, available):
        self._async_pending = False

        if not available:
            self._vte.feed(b"\x1b[33mNo providers configured.\x1b[0m\r\n")
            self._vte.feed(b"\x1b[90mSet API keys in Preferences > AI.\x1b[0m\r\n")
            self._input_shadow = ""
            return

        out = "\r\n\x1b[36mAvailable providers:\x1b[0m\r\n"
        self._provider_list = []
        for i, (prov, label, _info, fetched) in enumerate(available[:9]):
            num = i + 1
            icon = "\x1b[32m●\x1b[0m" if prov != "custom" or fetched else "\x1b[33m●\x1b[0m"
            out += f"  \x1b[33m[{num}]\x1b[0m {icon} {label}\r\n"
            self._provider_list.append((num, prov, fetched))
        out += "\x1b[90mPress 1..9 to select a provider, Esc to cancel.\x1b[0m\r\n"
        self._vte.feed(out.encode())

    def _cancel_async_wait(self):
        self._async_pending = False
        self._async_generation += 1
        self._provider_list = []
        self._model_list = []
        self._history_show_results = []
        self._vte.feed(b"\r\n\x1b[37mCancelled.\x1b[0m\r\n")
        self._input_shadow = ""
        self._exit_history_search_mode()

    def _select_provider_number(self, num):
        for n, prov, _fetched in self._provider_list:
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
        gen = self._async_generation
        threading.Thread(
            target=self._fetch_models_thread,
            args=(provider, key, model, base_url, gen),
            daemon=True,
        ).start()

    def _fetch_models_thread(self, provider, key, model, base_url, gen):
        if gen != self._async_generation:
            return
        models = AIClient.fetch_models(provider, key, base_url)
        if gen != self._async_generation:
            return
        GLib.idle_add(lambda g=gen: self._on_models_fetched(provider, key, model, base_url, models) if self._async_generation == g else None)

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
            updates = {"ai_last_provider": provider, "ai_provider": provider}
            if model:
                models = self._settings.get("ai_models", {})
                models[provider] = model
                updates["ai_models"] = models
            if base_url:
                urls = self._settings.get("ai_urls", {})
                urls[provider] = base_url
                updates["ai_urls"] = urls
            self._settings.set_many(updates)
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
            "                           Use -term to exclude, :sql SELECT ... for raw SQL\r\n"
            "  \x1b[33m/ai\x1b[0m                   Enter AI chat mode\r\n"
            "  \x1b[33m/ai off\x1b[0m               Exit AI chat mode\r\n"
            "  \x1b[33m/ai context N q\x1b[0m       Include last N terminal lines as context\r\n"
            "  \x1b[33m/connect\x1b[0m [prov]        Connect to AI provider\r\n"
            "  \x1b[33m/wnotes\x1b[0m [-file] txt    Save a timestamped note\r\n"
            "  \x1b[33m/onotes\x1b[0m [-file]         Open notes in editor\r\n"
            "  \x1b[33m/learn\x1b[0m <file>           Import commands from a file into history (no execution)\r\n"
            "  \x1b[33m/optimize\x1b[0m history       Dedup, vacuum and analyze the history database\r\n"
            "  \x1b[33m/help\x1b[0m                  Show this help\r\n"
            "  \x1b[33m/clear\x1b[0m                 Clear the screen\r\n"
            "\r\n"
            "  \x1b[90mTab\x1b[0m                    Autocomplete /commands\r\n"
            "  \x1b[90mTab Tab\x1b[0m                 History picker for the current command\r\n"
            "  \x1b[90mCtrl+R\x1b[0m                  History search\r\n"
            "  \x1b[90mCtrl+U\x1b[0m                  Kill line\r\n"
            "  \x1b[90mCtrl+W\x1b[0m                  Kill word\r\n"
            "  \x1b[90mCtrl+Click\x1b[0m              Open URL in browser\r\n"
            "  \x1b[90mCtrl+Shift+C/V\x1b[0m          Copy / Paste\r\n"
            "  \x1b[90mCtrl+Shift+T/N\x1b[0m          New Tab / Window\r\n"
            "  \x1b[90mAlt+1..9\x1b[0m                Replay history\r\n"
            "  \x1b[90mCtrl+Shift+F\x1b[0m           Search scrollback\r\n"
            "  \x1b[90mCtrl+Shift+M\x1b[0m           Set quickmark\r\n"
            "  \x1b[90mCtrl+M\x1b[0m                  Jump to next quickmark\r\n"
            "  \x1b[90mCtrl+Shift+B\x1b[0m           Toggle broadcast input\r\n"
            "  \x1b[90mCtrl+Shift+H\x1b[0m           Hint mode (select URLs/paths/commits with keyboard)\r\n"
            "  \x1b[90mCtrl+Shift+Y\x1b[0m           VI copy mode (hjkl scroll, v select, y yank)\r\n"
            "  \x1b[90m/ or ?\x1b[0m                 Search scrollback (when viewing history)\r\n"
            "\x1b[36m─────────────────────────\x1b[0m\r\n"
        )
        self._vte.feed(help_text.encode())

    def _trigger_bell_notification(self, exit_code):
        if not self._settings.get("bell_notification", False):
            return
        if not shutil.which("notify-send"):
            return
        try:
            cwd = self.get_cwd()
            status = "succeeded" if exit_code == 0 else f"failed (exit {exit_code})"
            subprocess.Popen(
                ["notify-send", "-a", "TPGK", "-i", "terminal",
                 "Command finished",
                 f"Command {status} in {cwd}"],
                start_new_session=True)
        except Exception:
            pass

    def _copy_url(self, url):
        if url:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(url, -1)

    def _show_search(self):
        if self._search_revealer.get_reveal_child():
            return
        self._search_revealer.set_reveal_child(True)
        self._search_entry.set_text("")
        self._search_entry.grab_focus()
        self._clear_search_highlights()

    def _hide_search(self):
        self._search_revealer.set_reveal_child(False)
        self._clear_search_highlights()
        self._search_results = []
        self._search_index = 0
        self._search_label.set_text("")
        self._vte.grab_focus()

    def _on_search_changed(self, entry):
        self._do_search()

    def _do_search(self):
        self._clear_search_highlights()
        self._search_results = []
        self._search_index = 0

        query = self._search_entry.get_text()
        if not query or len(query) < 2:
            self._search_label.set_text("type at least 2 characters")
            return

        use_regex = self._search_regex_btn.get_active()
        case_sensitive = self._search_case_btn.get_active()

        search_query = query
        if not use_regex:
            search_query = re.escape(query)
        if not case_sensitive:
            search_query = "(?i)" + search_query

        try:
            vte_regex = Vte.Regex.new_for_match(search_query, -1, Vte.REGEX_FLAGS_DEFAULT)
        except Exception:
            self._search_label.set_text("Invalid regex")
            return

        self._vte.search_set_regex(vte_regex, Vte.REGEX_FLAGS_DEFAULT)
        self._vte.search_set_wrap_around(True)
        found = self._vte.search_find_next()
        if found:
            self._search_label.set_text("Match")
        else:
            self._search_label.set_text("No matches")

    def _clear_search_highlights(self):
        for tag in self._search_tags:
            try:
                self._vte.match_remove(tag)
            except Exception:
                pass
        self._search_tags = []
        try:
            self._vte.search_set_regex(None, Vte.REGEX_FLAGS_DEFAULT)
        except Exception:
            pass

    def _on_search_key(self, entry, event):
        key = event.keyval
        state = event.state
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if key == Gdk.KEY_Escape:
            self._hide_search()
            return True
        if key == Gdk.KEY_Return or key == Gdk.KEY_KP_Enter:
            if shift:
                self._vte.search_find_previous()
            else:
                self._vte.search_find_next()
            return True
        if key == Gdk.KEY_Up:
            self._vte.search_find_previous()
            return True
        if key == Gdk.KEY_Down:
            self._vte.search_find_next()
            return True
        return False

    def _set_quickmark(self):
        try:
            _col, row = self._vte.get_cursor_position()
        except Exception:
            return
        if row < 0:
            return
        for existing in self._quickmarks:
            if abs(existing - row) < 3:
                return
        self._quickmarks.append(row)
        self._quickmarks.sort()
        self._quickmark_index = -1
        self._vte.feed(f"\r\n\x1b[32m+ Quickmark set at line {row}\x1b[0m\r\n".encode())

    def _jump_next_quickmark(self):
        if not self._quickmarks:
            return
        self._quickmark_index = (self._quickmark_index + 1) % len(self._quickmarks)
        target = self._quickmarks[self._quickmark_index]
        vadj = self._scroll.get_vadjustment()
        if vadj:
            vadj.set_value(target)

    def _remove_all_quickmarks(self):
        self._quickmarks = []
        self._quickmark_index = -1

    def feed_to_all_terminals(self, data_bytes):
        if not self._settings.get("broadcast_input", False):
            return False
        win = self._window
        if not hasattr(win, '_notebook'):
            return False
        for nb in (win._notebook, win._notebook2):
            for i in range(nb.get_n_pages()):
                page = nb.get_nth_page(i)
                if page is not self and hasattr(page, '_vte'):
                    try:
                        page._vte.feed_child(data_bytes)
                    except Exception:
                        pass
        return True

    def _is_at_prompt(self):
        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return True
        bottom = max(0.0, vadj.get_upper() - vadj.get_page_size())
        return vadj.get_value() >= bottom - 0.5

    def _cell_to_overlay_coords(self, col, row):
        cw = self._vte.get_char_width()
        ch = self._vte.get_char_height()
        vadj = self._scroll.get_vadjustment()
        scroll_row = vadj.get_value() if vadj else 0.0
        ok, vx, vy = self._vte.translate_coordinates(self._overlay, 0, 0)
        padding = self._settings.get("window_padding_horizontal", 2)
        cell_x = padding + 8 + col * cw
        cell_y = (row - scroll_row) * ch
        return (vx + cell_x, vy + cell_y)

    @staticmethod
    def _generate_hint_labels(count):
        labels = []
        chars = _HINT_CHARS
        for c in chars:
            labels.append(c)
            if len(labels) >= count:
                return labels[:count]
        for c1 in chars:
            for c2 in chars:
                labels.append(c1 + c2)
                if len(labels) >= count:
                    return labels[:count]
        for c1 in chars:
            for c2 in chars:
                for c3 in chars:
                    labels.append(c1 + c2 + c3)
                    if len(labels) >= count:
                        return labels[:count]
        return labels[:count]

    def _activate_hints(self):
        if self._hints_active:
            return
        self._hints_active = True
        self._hints_buffer = ""
        self._hints_map = {}
        vte_w = self._vte.get_allocated_width()
        self._hints_fixed.set_size_request(vte_w, -1)
        self._hints_fixed.show_all()
        matches = self._scan_for_hints()
        labels = self._generate_hint_labels(len(matches))
        for i, (match_type, match_text, col, row) in enumerate(matches):
            label = labels[i]
            self._hints_map[label] = (match_type, match_text)
            x, y = self._cell_to_overlay_coords(col, row)
            lbl = Gtk.Label(label=label)
            lbl.get_style_context().add_class("tpgk-hint-label")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_valign(Gtk.Align.START)
            lbl.show()
            self._hints_fixed.put(lbl, int(x), int(y))
        if self._hints_map:
            self._vte.feed(b"\r\n\x1b[90mType hint label to select, Esc to cancel.\x1b[0m\r\n")

    def _deactivate_hints(self):
        self._hints_active = False
        self._hints_buffer = ""
        for child in self._hints_fixed.get_children():
            self._hints_fixed.remove(child)
        self._hints_fixed.hide()
        self._hints_map = {}

    def _handle_hint_key(self, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self._deactivate_hints()
            return True
        text = event.string
        if not text or len(text) != 1 or ord(text[0]) < 0x20:
            return True
        self._hints_buffer += text
        if self._hints_buffer in self._hints_map:
            self._perform_hint_action(self._hints_map[self._hints_buffer])
            self._deactivate_hints()
            return True
        matching_prefixes = [k for k in self._hints_map if k.startswith(self._hints_buffer)]
        if not matching_prefixes:
            self._deactivate_hints()
            return True
        return True

    def _perform_hint_action(self, match_info):
        match_type, match_text = match_info
        if match_type == "url":
            self._open_url(match_text)
        elif match_type == "path":
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(match_text, -1)
            expanded = os.path.expanduser(match_text)
            if os.path.isdir(expanded):
                subprocess.Popen(["xdg-open", expanded], start_new_session=True)
            elif os.path.isfile(expanded):
                subprocess.Popen(["xdg-open", expanded], start_new_session=True)
            else:
                self._vte.feed(
                    f"\r\n\x1b[32mPath copied: {match_text}\x1b[0m\r\n".encode()
                )
        elif match_type in ("git-sha", "ip"):
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(match_text, -1)
            self._vte.feed(
                f"\r\n\x1b[32mCopied: {match_text}\x1b[0m\r\n".encode()
            )

    def _scan_for_hints(self):
        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return []
        scroll_top = int(vadj.get_value())
        page_size = int(vadj.get_page_size())
        if page_size <= 0:
            return []
        first_row = max(0, scroll_top - 1)
        last_row = scroll_top + page_size + 1
        matches = []
        try:
            text, _attrs = self._vte.get_text_range_format(
                Vte.Format.TEXT, first_row, 0, last_row, 0)
        except Exception:
            return matches
        if not text:
            return matches
        lines = text.split("\n")
        for i, line in enumerate(lines):
            row = first_row + i
            if row > last_row:
                break
            for m in _HINT_URL_RE.finditer(line):
                matches.append(("url", m.group(0), m.start(), row))
            for m in _HINT_PATH_RE.finditer(line):
                p = m.group(0).strip()
                if len(p) >= 3:
                    matches.append(("path", p, m.start(), row))
            for m in _HINT_GIT_SHA_RE.finditer(line):
                sha = m.group(1)
                if not re.match(r'^\d+$', sha) and len(sha) >= 7:
                    matches.append(("git-sha", sha, m.start(), row))
            for m in _HINT_IP_RE.finditer(line):
                parts = m.group(1).split(".")
                if all(0 <= int(p) <= 255 for p in parts):
                    matches.append(("ip", m.group(1), m.start(), row))
        max_matches = len(_HINT_CHARS) + len(_HINT_CHARS) * len(_HINT_CHARS)
        return matches[:max_matches]

    def _activate_vi_copy(self):
        if self._vi_copy_active:
            return
        self._vi_copy_active = True
        self._vi_visual_active = False
        self._vi_selection_start = -1
        self._vi_selection_end = -1
        self._vi_last_key = None
        self._vi_last_key_time = 0
        self._vi_overlay_area.set_size_request(
            self._vte.get_allocated_width(),
            self._vte.get_allocated_height())
        self._vi_overlay_area.show_all()
        self._vte.feed(b"\r\n\x1b[90mVI Copy Mode: hjkl scroll, v select, y yank, / search, Esc exit\x1b[0m\r\n")

    def _deactivate_vi_copy(self):
        self._vi_copy_active = False
        self._vi_visual_active = False
        self._vi_selection_start = -1
        self._vi_selection_end = -1
        self._vi_overlay_area.hide()

    def _handle_vi_copy_key(self, event):
        key = event.keyval
        ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)
        if key == Gdk.KEY_Escape:
            self._deactivate_vi_copy()
            return True
        if key == Gdk.KEY_C or key == Gdk.KEY_c:
            if ctrl:
                self._deactivate_vi_copy()
                return True
        if ctrl:
            if key == Gdk.KEY_U or key == Gdk.KEY_u:
                self._vi_scroll_page(up=True)
                return True
            if key == Gdk.KEY_D or key == Gdk.KEY_d:
                self._vi_scroll_page(up=False)
                return True
            return True
        if key == Gdk.KEY_j:
            self._vi_scroll(1)
        elif key == Gdk.KEY_k:
            self._vi_scroll(-1)
        elif key == Gdk.KEY_h:
            self._vi_scroll_h(-3)
        elif key == Gdk.KEY_l:
            self._vi_scroll_h(3)
        elif key == Gdk.KEY_w:
            self._vi_scroll(5)
        elif key == Gdk.KEY_b:
            self._vi_scroll(-5)
        elif key == Gdk.KEY_v:
            self._vi_toggle_visual()
        elif key == Gdk.KEY_V:
            self._vi_toggle_visual()
        elif key == Gdk.KEY_y:
            self._vi_yank_selection()
        elif key == Gdk.KEY_slash:
            self._show_search()
            return True
        elif key == Gdk.KEY_question:
            self._show_search()
            return True
        elif key == Gdk.KEY_g:
            now = GLib.get_monotonic_time()
            if self._vi_last_key == Gdk.KEY_g and (now - self._vi_last_key_time) < 1_000_000:
                self._vi_scroll_to_top()
                self._vi_last_key = None
            else:
                self._vi_last_key = Gdk.KEY_g
                self._vi_last_key_time = now
        elif key == Gdk.KEY_G:
            self._vi_scroll_to_bottom()
        else:
            return True
        if self._vi_visual_active:
            self._vi_overlay_area.queue_draw()
        return True

    def _vi_scroll(self, lines):
        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return
        new_val = vadj.get_value() + lines
        bottom = max(0.0, vadj.get_upper() - vadj.get_page_size())
        new_val = max(0.0, min(bottom, new_val))
        vadj.set_value(new_val)
        if self._vi_visual_active:
            row = int(vadj.get_value())
            if self._vi_selection_start < 0:
                self._vi_selection_start = row
            self._vi_selection_end = row

    def _vi_scroll_h(self, cols):
        hadj = self._scroll.get_hadjustment()
        if not hadj:
            return
        cw = self._vte.get_char_width()
        if cw <= 0:
            cw = 8
        new_val = hadj.get_value() + cols * cw
        new_val = max(0.0, min(hadj.get_upper() - hadj.get_page_size(), new_val))
        hadj.set_value(new_val)

    def _vi_scroll_to_top(self):
        vadj = self._scroll.get_vadjustment()
        if vadj:
            vadj.set_value(0)

    def _vi_scroll_to_bottom(self):
        vadj = self._scroll.get_vadjustment()
        if vadj:
            bottom = max(0.0, vadj.get_upper() - vadj.get_page_size())
            vadj.set_value(bottom)

    def _vi_scroll_page(self, up):
        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return
        page = vadj.get_page_size() * 0.5
        delta = -page if up else page
        new_val = vadj.get_value() + delta
        bottom = max(0.0, vadj.get_upper() - vadj.get_page_size())
        new_val = max(0.0, min(bottom, new_val))
        vadj.set_value(new_val)

    def _vi_toggle_visual(self):
        if self._vi_visual_active:
            self._vi_visual_active = False
            self._vi_selection_start = -1
            self._vi_selection_end = -1
            self._vi_overlay_area.queue_draw()
            return
        self._vi_visual_active = True
        vadj = self._scroll.get_vadjustment()
        if vadj:
            self._vi_selection_start = int(vadj.get_value())
            self._vi_selection_end = int(vadj.get_value())
            self._vi_overlay_area.queue_draw()

    def _vi_yank_selection(self):
        if self._vi_visual_active and self._vi_selection_start >= 0:
            start = min(self._vi_selection_start, self._vi_selection_end)
            end = max(self._vi_selection_start, self._vi_selection_end)
            if end > start + 500:
                end = start + 500
            try:
                text, _ = self._vte.get_text_range_format(
                    Vte.Format.TEXT, start, 0, end + 1, 0)
            except Exception:
                text = ""
            if text:
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                clipboard.set_text(text, -1)
                self._vte.feed(
                    f"\r\n\x1b[32m{len(text.splitlines())} lines copied\x1b[0m\r\n".encode()
                )
            else:
                self._vte.feed(b"\r\n\x1b[33mNo text selected.\x1b[0m\r\n")
            self._deactivate_vi_copy()
        else:
            self._deactivate_vi_copy()

    def _draw_vi_overlay(self, widget, cr):
        if not self._vi_visual_active:
            return
        if self._vi_selection_start < 0 or self._vi_selection_end < 0:
            return
        vadj = self._scroll.get_vadjustment()
        if not vadj:
            return
        scroll_row = vadj.get_value()
        ch = self._vte.get_char_height()
        if ch <= 0:
            ch = 16
        ok, vx, vy = self._vte.translate_coordinates(self._overlay, 0, 0)
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        start = min(self._vi_selection_start, self._vi_selection_end)
        end = max(self._vi_selection_start, self._vi_selection_end)
        padding = self._settings.get("window_padding_horizontal", 2)
        x = padding + 8
        for row in range(start, end + 1):
            y = (row - scroll_row) * ch
            if 0 <= y <= height:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.12)
                cr.rectangle(x, vy + y, width - x, ch)
                cr.fill()
        cur_y = (int(vadj.get_value()) - scroll_row) * ch
        cr.set_source_rgba(0.988, 0.816, 0.31, 0.8)
        cr.rectangle(0, vy + cur_y, width, 2)
        cr.fill()



def _hex_to_gdk(hex_color: str):
    color = Gdk.RGBA()
    color.parse(hex_color)
    return color
