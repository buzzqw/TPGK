import os
import sys
import shutil
import signal
import subprocess

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gtk, Gdk, GLib, Vte
from tpgk.settings import Settings
from tpgk.terminal import TerminalBox


SIGNALS = [
    ("SIGHUP (1)", signal.SIGHUP),
    ("SIGINT (2)", signal.SIGINT),
    ("SIGQUIT (3)", signal.SIGQUIT),
    ("SIGILL (4)", signal.SIGILL),
    ("SIGABRT (6)", signal.SIGABRT),
    ("SIGKILL (9)", signal.SIGKILL),
    ("SIGUSR1 (10)", signal.SIGUSR1),
    ("SIGSEGV (11)", signal.SIGSEGV),
    ("SIGUSR2 (12)", signal.SIGUSR2),
    ("SIGPIPE (13)", signal.SIGPIPE),
    ("SIGTERM (15)", signal.SIGTERM),
    ("SIGSTOP (19)", signal.SIGSTOP),
    ("SIGTSTP (20)", signal.SIGTSTP),
    ("SIGCONT (18)", signal.SIGCONT),
]

ENCODINGS = [
    "UTF-8", "ISO-8859-1", "ISO-8859-15", "UTF-16",
    "UTF-16BE", "UTF-16LE",
    "CP1252", "CP850", "ASCII", "KOI8-R", "Shift_JIS", "EUC-JP", "GBK",
]

EUPL_LICENSE_TEXT = """EUROPEAN UNION PUBLIC LICENCE v. 1.2

This software is licensed under the European Union Public Licence (EUPL) version 1.2.

The full license text is available at:
https://joinup.ec.europa.eu/collection/eupl/eupl-text-eupl-12

Copyright (c) 2026 Andres Zanzani

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

The Software may not be used for military purposes or in any way that violates
human rights as defined by the Charter of Fundamental Rights of the European Union.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Compatible licenses under EUPL 1.2 include:
- GNU General Public License (GPL) v. 2, v. 3
- GNU Affero General Public License (AGPL) v. 3
- Eclipse Public License (EPL) v. 1.0, v. 2.0
- Mozilla Public License (MPL) v. 2.0
- GNU Lesser General Public License (LGPL) v. 2.1, v. 3.0
- CeCILL v. 2.0, v. 2.1
"""


def _detect_file_manager(settings: Settings) -> str:
    fm = settings.get("file_manager", "")
    if fm and shutil.which(fm):
        return fm
    for candidate in ["nemo", "thunar", "dolphin", "nautilus", "pcmanfm",
                      "caja", "nemo-desktop", "spacefm"]:
        if shutil.which(candidate):
            return candidate
    return ""


class _DetachedWindow(Gtk.Window):
    def __init__(self, terminal: TerminalBox, title: str):
        super().__init__(title=f"TPGK - {title}")
        self._settings = Settings()
        self._terminal = terminal
        self._apply_window_size()

        self._stats_label = Gtk.Label()
        self._stats_label.set_halign(Gtk.Align.START)
        self._stats_label.get_style_context().add_class("tpgk-stats-label")
        self._stats_label.set_no_show_all(True)
        self._stats_source_id = 0

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        self._accel_group = Gtk.AccelGroup()
        self.add_accel_group(self._accel_group)

        self._build_headerbar(title)

        vbox.pack_start(self._menubar, False, False, 0)
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        vbox.pack_start(terminal, True, True, 0)
        vbox.pack_end(self._stats_label, False, False, 0)

        self._toolbar.set_visible(self._settings.get("show_toolbar", False))
        self._menubar.set_visible(self._settings.get("show_menubar", True))
        self._apply_stats_visibility()

        self._settings.connect(self._apply_window_size)

        self.connect("delete-event", lambda *a: self._on_close())
        self.connect("key-press-event", self._on_window_key)

        self.show_all()
        GLib.idle_add(self._populate_menus)
        GLib.idle_add(terminal._vte.grab_focus)

    def _apply_window_size(self):
        cols = self._settings.get("terminal_columns", 80)
        rows = self._settings.get("terminal_rows", 24)
        font_size = self._settings.get("font_size", 12)
        cw = max(int(font_size * 0.6), 5)
        ch = max(int(font_size * 1.45), 10)
        self.resize(cols * cw + 60, rows * ch + 120)

    def set_title(self, title):
        super().set_title(title)
        if getattr(self, "_headerbar", None) is not None:
            self._headerbar.set_title(title)

    def _build_headerbar(self, title):
        from tpgk.icons import icon_button

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title(f"TPGK - {title}")
        self._headerbar = header

        self._toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        new_win_btn = icon_button("window-new-symbolic",
                                   tooltip="Open a new terminal window (Ctrl+Shift+N)")
        new_win_btn.connect("clicked", lambda *a: self._on_new_window())
        self._toolbar.pack_start(new_win_btn, False, False, 0)

        self._toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        copy_btn = icon_button("edit-copy-symbolic", tooltip="Copy selected text (Ctrl+Shift+C)")
        copy_btn.connect("clicked", lambda *a: self._terminal.copy())
        self._toolbar.pack_start(copy_btn, False, False, 0)

        paste_btn = icon_button("edit-paste-symbolic", tooltip="Paste from clipboard (Ctrl+Shift+V)")
        paste_btn.connect("clicked", lambda *a: self._terminal.paste())
        self._toolbar.pack_start(paste_btn, False, False, 0)

        header.pack_start(self._toolbar)

        self._menubar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._menubar.get_style_context().add_class("tpgk-menu-row")
        self._menu_buttons = []
        for lbl in ("File", "Edit", "View", "Terminal", "Help"):
            btn = Gtk.MenuButton(label=lbl)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            self._menubar.pack_start(btn, False, False, 0)
            self._menu_buttons.append(btn)

        self.set_titlebar(header)

    def _build_menu(self):
        menus = []

        file_menu = Gtk.Menu()

        self._menu_item(file_menu, "New Window", lambda *a: self._on_new_window(), "<Primary><Shift>N",
                        "Open a new TPGK terminal window")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Open File Manager Here", lambda *a: self._open_fm(),
                        tooltip="Open the file manager in the current terminal working directory")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Close Window", lambda *a: self._on_close(), "<Primary><Shift>Q",
                        "Close this window")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Quit", lambda *a: self._on_close(), "<Primary>Q",
                        "Quit – close this window")

        menus.append(("File", file_menu))

        edit_menu = Gtk.Menu()

        self._menu_item(edit_menu, "Copy", lambda *a: self._terminal.copy(), "<Primary><Shift>C",
                        "Copy selected text to clipboard")
        self._menu_item(edit_menu, "Paste", lambda *a: self._terminal.paste(), "<Primary><Shift>V",
                        "Paste clipboard content into the terminal")
        self._menu_item(edit_menu, "Paste Selection", lambda *a: self._terminal.paste_selection(),
                        tooltip="Paste the primary selection (middle-click paste)")
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(edit_menu, "Select All", lambda *a: self._terminal.select_all(), "<Primary><Shift>A",
                        "Select all text in the terminal")
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(edit_menu, "Preferences...", lambda *a: self._open_settings(),
                        "Open the TPGK settings dialog")

        menus.append(("Edit", edit_menu))

        view_menu = Gtk.Menu()

        self._show_menubar_action = self._check_menu_item(
            view_menu, "Always Show Menus", self._on_toggle_show_menubar,
            self._settings.get("show_menubar", True),
            "Keep the File/Edit/View/... menu buttons always visible in the header bar")
        self._show_toolbar_action = self._check_menu_item(
            view_menu, "Always Show Quick Actions", self._on_toggle_show_toolbar,
            self._settings.get("show_toolbar", False),
            "Always show the quick-action buttons in the header bar")
        self._show_stats_action = self._check_menu_item(
            view_menu, "Show System Stats", self._on_toggle_show_stats,
            self._settings.get("show_stats", False),
            "Show CPU, RAM and Disk usage at the bottom of the window")

        view_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(view_menu, "Full Screen", lambda *a: self._toggle_fullscreen(), "F11",
                        "Toggle full-screen mode")

        view_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(view_menu, "Zoom In", lambda *a: self._terminal.zoom_in(), "<Primary>plus",
                        "Increase terminal font size")
        self._menu_item(view_menu, "Zoom Out", lambda *a: self._terminal.zoom_out(), "<Primary>minus",
                        "Decrease terminal font size")
        self._menu_item(view_menu, "Zoom Reset", lambda *a: self._terminal.zoom_reset(), "<Primary>0",
                        "Reset terminal font size to default")

        menus.append(("View", view_menu))

        term_menu = Gtk.Menu()

        self._menu_item(term_menu, "Set Title...", lambda *a: self._set_title_dialog(), "<Primary><Shift>S",
                        "Set a custom title for this window")
        term_menu.append(Gtk.SeparatorMenuItem())

        self._encoding_menu = Gtk.Menu()
        enc_item = Gtk.MenuItem(label="Set Encoding")
        enc_item.set_submenu(self._encoding_menu)
        self._encoding_actions = []
        for label in ENCODINGS:
            enc_name = label.split(" ")[0]
            action = self._check_menu_item(self._encoding_menu, label,
                                           lambda *a, e=enc_name: self._set_encoding(e),
                                           self._settings.get("encoding", "UTF-8") == enc_name,
                                           f"Set terminal character encoding to {enc_name}")
            self._encoding_actions.append((action, enc_name))
        term_menu.append(enc_item)

        term_menu.append(Gtk.SeparatorMenuItem())

        self._signal_menu = Gtk.Menu()
        sig_item = Gtk.MenuItem(label="Send Signal")
        sig_item.set_submenu(self._signal_menu)
        for label, sig in SIGNALS:
            self._menu_item(self._signal_menu, label, lambda *a, s=sig: self._send_signal(s),
                            tooltip=f"Send {label} to the foreground process")
        term_menu.append(sig_item)

        term_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(term_menu, "Reset", lambda *a: self._terminal.reset(clear=False), "<Primary><Shift>R",
                        "Soft reset the terminal emulator state")
        self._menu_item(term_menu, "Reset and Clear", lambda *a: self._terminal.reset(clear=True), "<Primary><Shift>X",
                        "Reset the terminal and clear the scrollback buffer")

        term_menu.append(Gtk.SeparatorMenuItem())

        self._read_only_action = self._check_menu_item(
            term_menu, "Read-Only", self._on_toggle_read_only, False,
            "Toggle read-only mode (blocks keyboard input)")

        menus.append(("Terminal", term_menu))

        help_menu = Gtk.Menu()
        self._menu_item(help_menu, "About", lambda *a: self._show_about(),
                        "Show information about TPGK")
        menus.append(("Help", help_menu))

        for _, category_menu in menus:
            category_menu.show_all()
        return menus

    def _populate_menus(self):
        menus = self._build_menu()
        for btn, (label, menu) in zip(self._menu_buttons, menus):
            btn.set_popup(menu)
        self._menu_buttons = []
        return False

    def _menu_item(self, menu, label, callback, accel=None, tooltip=None):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", callback)
        if accel:
            key, mod = Gtk.accelerator_parse(accel)
            if key:
                item.add_accelerator("activate", self._accel_group, key, mod,
                                     Gtk.AccelFlags.VISIBLE)
        if tooltip:
            item.set_tooltip_text(tooltip)
        menu.append(item)
        return item

    def _check_menu_item(self, menu, label, callback, active=False, tooltip=None):
        item = Gtk.CheckMenuItem(label=label)
        item.set_active(active)
        item.connect("activate", callback)
        if tooltip:
            item.set_tooltip_text(tooltip)
        menu.append(item)
        return item

    def _on_new_window(self, *a):
        env = os.environ.copy()
        env["TPGK_RELOAD_MODULES"] = "1"
        subprocess.Popen([sys.executable, "-m", "tpgk"], env=env, start_new_session=True)

    def _open_fm(self, *a):
        fm = _detect_file_manager(self._settings)
        if not fm:
            return
        cwd = self._terminal.get_cwd()
        subprocess.Popen([fm, cwd], start_new_session=True)

    def _open_settings(self, *a):
        from tpgk.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.run()
        dialog.destroy()

    def _on_toggle_show_menubar(self, check):
        self._settings.set("show_menubar", check.get_active())
        self._menubar.set_visible(check.get_active())

    def _on_toggle_show_toolbar(self, check):
        self._settings.set("show_toolbar", check.get_active())
        self._toolbar.set_visible(check.get_active())

    def _on_toggle_show_stats(self, check):
        self._settings.set("show_stats", check.get_active())
        self._apply_stats_visibility()

    def _apply_stats_visibility(self):
        visible = self._settings.get("show_stats", False)
        self._stats_label.set_visible(visible)
        if visible:
            self._start_stats_timer()
        else:
            self._stop_stats_timer()

    def _start_stats_timer(self):
        if self._stats_source_id:
            return
        self._refresh_stats()
        self._stats_source_id = GLib.timeout_add_seconds(3, self._refresh_stats)

    def _stop_stats_timer(self):
        if self._stats_source_id:
            GLib.source_remove(self._stats_source_id)
            self._stats_source_id = 0

    def _refresh_stats(self):
        from tpgk.system_stats import collect
        term = self._terminal if self._terminal else None
        is_ssh = term.is_ssh() if term else False
        stats = collect(is_ssh)
        self._stats_label.set_text(stats)
        return True

    def _toggle_fullscreen(self, *a):
        if self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _set_title_dialog(self, *a):
        dialog = Gtk.Dialog(title="Set Title", transient_for=self,
                            modal=True, destroy_with_parent=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Set", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_text(self.get_title().replace("TPGK - ", ""))
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            title = entry.get_text().strip()
            if title:
                self.set_title(f"TPGK - {title}")
        dialog.destroy()

    def _set_encoding(self, encoding: str):
        self._terminal.set_encoding(encoding)
        title = self.get_title().split(" [")[0]
        self.set_title(f"{title} [{encoding}]")
        self._settings.set("encoding", encoding)
        for action, enc_name in self._encoding_actions:
            action.set_active(enc_name == encoding)

    def _send_signal(self, sig: int):
        self._terminal.kill(sig)

    def _on_toggle_read_only(self, check):
        self._terminal.set_read_only(check.get_active())

    def _show_about(self, *a):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("TPGK")
        dialog.set_version("1.1.0")
        dialog.set_comments("Advanced terminal emulator powered by VTE")
        dialog.set_copyright("Andres Zanzani")
        dialog.set_license_type(Gtk.License.CUSTOM)
        dialog.set_license(EUPL_LICENSE_TEXT)
        dialog.run()
        dialog.destroy()

    def _on_close(self, *a):
        self._terminal.terminate()
        self.destroy()

    def _on_window_key(self, widget, event):
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        key = event.keyval

        if ctrl and key == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        if key == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        return False

    # Fix #4a: expose the same public signals that TerminalBox._on_key_press expects
    def new_tab_signal(self):
        self._on_new_window()

    def close_tab_signal(self):
        self._on_close()

    def close_window_signal(self):
        self._on_close()

    def set_title_dialog(self):
        self._set_title_dialog()

    def reset_terminal(self):
        self._terminal.reset(clear=False)

    def reset_and_clear(self):
        self._terminal.reset(clear=True)

    def set_tab_title_from_terminal(self, term, title):
        self.set_title(f"TPGK - {title}")

    def split_signal(self, mode):
        pass

    def focus_other_pane_signal(self):
        pass


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self._settings = Settings()

        self.set_title("TPGK Terminal")
        cols = self._settings.get("terminal_columns", 80)
        rows = self._settings.get("terminal_rows", 24)
        font_size = self._settings.get("font_size", 12)
        cw = max(int(font_size * 0.6), 5)
        ch = max(int(font_size * 1.45), 10)
        self.set_default_size(cols * cw + 60, rows * ch + 120)

        if self._settings.get("enable_transparency", False):
            self.set_app_paintable(True)
            self.set_visual(self.get_screen().get_rgba_visual())
        opacity = round(self._settings.get("opacity", 1.0), 2)
        if opacity < 1.0:
            self.set_opacity(opacity)

        self._paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._paned.set_wide_handle(True)

        self._notebook = Gtk.Notebook()
        self._notebook.set_scrollable(True)
        self._notebook.set_show_border(False)
        self._notebook.connect("switch-page", self._on_switch_tab)
        self._notebook.connect("page-reordered", lambda *a: self._update_tabs_menu())
        self._notebook.connect("page-removed", lambda *a: self._on_page_removed())

        self._notebook2 = Gtk.Notebook()
        self._notebook2.set_scrollable(True)
        self._notebook2.set_show_border(False)
        self._notebook2.set_no_show_all(True)
        self._notebook2.hide()
        self._notebook2.connect("switch-page", self._on_switch_tab)
        self._notebook2.connect("page-removed", lambda *a: self._on_page_removed())

        self._paned.pack1(self._notebook, True, True)
        self._paned.pack2(self._notebook2, True, True)

        self._needs_handle_fix = False
        self._split_mode = "single"

        self._tab_base_titles = {}
        self._tab_labels = {}
        self._widget_nb_map = {}
        self._next_tab_number = 1
        self._current_pages = {}

        self._accel_group = Gtk.AccelGroup()
        self.add_accel_group(self._accel_group)

        self._build_headerbar()

        self._stats_label = Gtk.Label()
        self._stats_label.set_halign(Gtk.Align.START)
        self._stats_label.get_style_context().add_class("tpgk-stats-label")
        self._stats_label.set_no_show_all(True)
        self._stats_source_id = 0

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.pack_start(self._menubar, False, False, 0)
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        vbox.pack_start(self._paned, True, True, 0)
        vbox.pack_end(self._stats_label, False, False, 0)
        self.add(vbox)

        self.connect("delete-event", self._on_close)
        self.connect("key-press-event", self._on_window_key)

        self.show_all()
        GLib.idle_add(self._populate_menus)
        self._toolbar.set_visible(self._settings.get("show_toolbar", False))
        self._menubar.set_visible(self._settings.get("show_menubar", True))
        self._apply_stats_visibility()

        self._apply_tab_colors()

        self._settings.connect(self._apply_tab_colors)
        self._settings.connect(self._apply_window_size)

        GLib.idle_add(self._fix_paned_position)
        GLib.idle_add(self._add_new_tab)

    def _apply_window_size(self):
        cols = self._settings.get("terminal_columns", 80)
        rows = self._settings.get("terminal_rows", 24)
        font_size = self._settings.get("font_size", 12)
        cw = max(int(font_size * 0.6), 5)
        ch = max(int(font_size * 1.45), 10)
        w = cols * cw + 60
        h = rows * ch + 120
        self.resize(w, h)

    def set_title(self, title):
        super().set_title(title)
        if getattr(self, "_headerbar", None) is not None:
            self._headerbar.set_title(title)

    def _fix_paned_position(self):
        self._paned.set_position(99999)
        self._needs_handle_fix = False

    def _active_notebook(self):
        if self._split_mode == "single":
            return self._notebook
        focus = self.get_focus()
        if focus:
            parent = focus.get_parent()
            while parent:
                if parent is self._notebook2:
                    return self._notebook2
                if parent is self._notebook:
                    return self._notebook
                parent = parent.get_parent() if hasattr(parent, 'get_parent') else None
        for i in range(self._notebook.get_n_pages()):
            page = self._notebook.get_nth_page(i)
            if page and page._vte and page._vte.is_focus():
                return self._notebook
        for i in range(self._notebook2.get_n_pages()):
            page = self._notebook2.get_nth_page(i)
            if page and page._vte and page._vte.is_focus():
                return self._notebook2
        return self._notebook

    def _current_terminal(self):
        for nb in (self._notebook, self._notebook2):
            idx = nb.get_current_page()
            if idx >= 0:
                return nb.get_nth_page(idx)
        return None

    def _find_terminal(self, term):
        if term is None:
            return None, -1
        for nb in (self._notebook, self._notebook2):
            idx = nb.page_num(term)
            if idx >= 0:
                return nb, idx
        return None, -1

    def _total_tabs(self):
        return self._notebook.get_n_pages() + self._notebook2.get_n_pages()

    def _apply_tab_colors(self):
        title_color = self._settings.get("tab_title_color", "")
        active_color = self._settings.get("tab_active_title_color", "")

        title_gdk = Gdk.RGBA()
        active_gdk = Gdk.RGBA()
        try:
            if title_color:
                title_gdk.parse(title_color)
            if active_color:
                active_gdk.parse(active_color)
        except Exception:
            return

        for nb in (self._notebook, self._notebook2):
            cur = self._current_pages.get(nb, nb.get_current_page())
            for i in range(nb.get_n_pages()):
                page = nb.get_nth_page(i)
                entry = self._tab_labels.get(page)
                if entry is None:
                    continue
                _, lbl = entry
                if i == cur and active_color:
                    lbl.override_color(Gtk.StateFlags.NORMAL, active_gdk)
                elif title_color:
                    lbl.override_color(Gtk.StateFlags.NORMAL, title_gdk)
                else:
                    lbl.override_color(Gtk.StateFlags.NORMAL, None)

    # ── Menubar ─────────────────────────────────────────────

    def _build_menu(self):
        menus = []

        file_menu = Gtk.Menu()

        self._menu_item(file_menu, "New Tab", self._on_new_tab, "<Primary><Shift>T",
                        "Open a new terminal tab in the current window")
        self._menu_item(file_menu, "New Window", self._on_new_window, "<Primary><Shift>N",
                        "Open a new TPGK terminal window")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Open File Manager Here", self._on_open_fm,
                        tooltip="Open the file manager in the current terminal working directory")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Close Tab", lambda *a: self._close_tab(), "<Primary><Shift>W",
                        "Close the current terminal tab")
        self._menu_item(file_menu, "Close Window", lambda *a: self._on_close(), "<Primary><Shift>Q",
                        "Close the current window")
        file_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(file_menu, "Quit", lambda *a: self._on_close(), "<Primary>Q",
                        "Quit TPGK (close all windows)")

        menus.append(("File", file_menu))

        edit_menu = Gtk.Menu()

        self._menu_item(edit_menu, "Copy", lambda *a: self._term_copy(), "<Primary><Shift>C",
                        "Copy selected text to clipboard")
        self._menu_item(edit_menu, "Paste", lambda *a: self._term_paste(), "<Primary><Shift>V",
                        "Paste clipboard content into the terminal")
        self._menu_item(edit_menu, "Paste Selection", lambda *a: self._term_paste_sel(),
                        tooltip="Paste the primary selection (middle-click paste)")
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(edit_menu, "Select All", lambda *a: self._term_select_all(), "<Primary><Shift>A",
                        "Select all text in the terminal")
        edit_menu.append(Gtk.SeparatorMenuItem())
        self._menu_item(edit_menu, "Preferences...", lambda *a: self._open_settings(),
                        "Open the TPGK settings dialog")

        menus.append(("Edit", edit_menu))

        view_menu = Gtk.Menu()

        self._split_menu = Gtk.Menu()
        split_item = Gtk.MenuItem(label="Split")
        split_item.set_submenu(self._split_menu)

        self._split_single_act = self._check_menu_item(
            self._split_menu, "Single Panel", lambda *a: self._set_split("single"), True,
            "Single terminal panel (no split)")
        self._split_v_act = self._check_menu_item(
            self._split_menu, "Split Vertical", lambda *a: self._set_split("vertical"), False,
            "Split the window vertically (left/right panels)")
        self._split_h_act = self._check_menu_item(
            self._split_menu, "Split Horizontal", lambda *a: self._set_split("horizontal"), False,
            "Split the window horizontally (top/bottom panels)")
        view_menu.append(split_item)

        view_menu.append(Gtk.SeparatorMenuItem())

        self._show_tabs_action = self._check_menu_item(
            view_menu, "Always Show Tabs", self._on_toggle_show_tabs,
            self._settings.get("show_tabs", True),
            "Show the tab bar even when only one tab is open")
        self._show_menubar_action = self._check_menu_item(
            view_menu, "Always Show Menus", self._on_toggle_show_menubar,
            self._settings.get("show_menubar", True),
            "Keep the File/Edit/View/... menu buttons always visible in the header bar")
        self._show_scrollbar_action = self._check_menu_item(
            view_menu, "Always Show Scrollbar", self._on_toggle_show_scrollbar,
            self._settings.get("scrollbar_position", "right") != "disabled",
            "Always show the vertical scrollbar")
        self._show_toolbar_action = self._check_menu_item(
            view_menu, "Always Show Quick Actions", self._on_toggle_show_toolbar,
            self._settings.get("show_toolbar", False),
            "Always show the quick-action buttons in the header bar")
        self._show_stats_action = self._check_menu_item(
            view_menu, "Show System Stats", self._on_toggle_show_stats,
            self._settings.get("show_stats", False),
            "Show CPU, RAM and Disk usage at the bottom of the window")

        view_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(view_menu, "Full Screen", lambda *a: self._toggle_fullscreen(), "F11",
                        "Toggle full-screen mode")

        view_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(view_menu, "Zoom In", lambda *a: self._zoom_in(), "<Primary>plus",
                        "Increase terminal font size")
        self._menu_item(view_menu, "Zoom Out", lambda *a: self._zoom_out(), "<Primary>minus",
                        "Decrease terminal font size")
        self._menu_item(view_menu, "Zoom Reset", lambda *a: self._zoom_reset(), "<Primary>0",
                        "Reset terminal font size to default")

        menus.append(("View", view_menu))

        term_menu = Gtk.Menu()

        self._menu_item(term_menu, "Set Title...", lambda *a: self._set_title_dialog(), "<Primary><Shift>S",
                        "Set a custom title for the current tab")
        term_menu.append(Gtk.SeparatorMenuItem())

        self._encoding_menu = Gtk.Menu()
        enc_item = Gtk.MenuItem(label="Set Encoding")
        enc_item.set_submenu(self._encoding_menu)
        self._encoding_actions = []
        for label in ENCODINGS:
            enc_name = label.split(" ")[0]
            action = self._check_menu_item(self._encoding_menu, label,
                                           lambda *a, e=enc_name: self._set_encoding(e),
                                           self._settings.get("encoding", "UTF-8") == enc_name,
                                           f"Set terminal character encoding to {enc_name}")
            self._encoding_actions.append((action, enc_name))
        term_menu.append(enc_item)

        term_menu.append(Gtk.SeparatorMenuItem())

        self._signal_menu = Gtk.Menu()
        sig_item = Gtk.MenuItem(label="Send Signal")
        sig_item.set_submenu(self._signal_menu)
        for label, sig in SIGNALS:
            self._menu_item(self._signal_menu, label, lambda *a, s=sig: self._send_signal(s),
                            tooltip=f"Send {label} to the foreground process")
        term_menu.append(sig_item)

        term_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(term_menu, "Reset", lambda *a: self._reset_terminal(), "<Primary><Shift>R",
                        "Soft reset the terminal emulator state")
        self._menu_item(term_menu, "Reset and Clear", lambda *a: self._reset_and_clear(), "<Primary><Shift>X",
                        "Reset the terminal and clear the scrollback buffer")

        term_menu.append(Gtk.SeparatorMenuItem())

        self._read_only_action = self._check_menu_item(
            term_menu, "Read-Only", self._on_toggle_read_only, False,
            "Toggle read-only mode (blocks keyboard input)")

        term_menu.append(Gtk.SeparatorMenuItem())

        self._menu_item(term_menu, "Previous Pane", lambda *a: self._focus_other_pane(), "<Primary><Alt>Page_Up",
                        "Switch focus to the other split pane")
        self._menu_item(term_menu, "Previous Tab", lambda *a: self._prev_tab(), "<Primary>Page_Up",
                        "Switch to the previous tab")
        self._menu_item(term_menu, "Next Tab", lambda *a: self._next_tab(), "<Primary>Page_Down",
                        "Switch to the next tab")
        self._menu_item(term_menu, "Move Tab Left", lambda *a: self._move_tab(-1), "<Primary><Shift>Page_Up",
                        "Move the current tab one position to the left")
        self._menu_item(term_menu, "Move Tab Right", lambda *a: self._move_tab(1), "<Primary><Shift>Page_Down",
                        "Move the current tab one position to the right")
        self._menu_item(term_menu, "Detach Tab", lambda *a: self._detach_tab(),
                        "Detach the current tab into a separate window with full menu")

        menus.append(("Terminal", term_menu))

        self._tabs_menu = Gtk.Menu()
        menus.append(("Tabs", self._tabs_menu))

        help_menu = Gtk.Menu()
        self._menu_item(help_menu, "About", lambda *a: self._show_about(),
                        "Show information about TPGK")
        menus.append(("Help", help_menu))

        for _, category_menu in menus:
            category_menu.show_all()
        return menus

    def _populate_menus(self):
        menus = self._build_menu()
        for btn, (label, menu) in zip(self._menu_buttons, menus):
            btn.set_popup(menu)
        self._menu_buttons = []
        return False

    def _menu_item(self, menu, label, callback, accel=None, tooltip=None):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", callback)
        if accel:
            key, mod = Gtk.accelerator_parse(accel)
            if key:
                item.add_accelerator("activate", self._accel_group, key, mod,
                                     Gtk.AccelFlags.VISIBLE)
        if tooltip:
            item.set_tooltip_text(tooltip)
        menu.append(item)
        return item

    def _check_menu_item(self, menu, label, callback, active=False, tooltip=None):
        item = Gtk.CheckMenuItem(label=label)
        item.set_active(active)
        item.connect("activate", callback)
        if tooltip:
            item.set_tooltip_text(tooltip)
        menu.append(item)
        return item

    # ── Split modes ──────────────────────────────────────────

    def _set_split(self, mode):
        if getattr(self, '_splitting', False):
            return
        self._splitting = True
        try:
            self._split_mode = mode
            if mode == "single":
                while self._notebook2.get_n_pages() > 0:
                    self._move_tab_between(self._notebook2, self._notebook, 0)
                self._notebook2.hide()
                self._paned.set_position(99999)
                self._split_single_act.set_active(True)
                self._split_v_act.set_active(False)
                self._split_h_act.set_active(False)
            elif mode == "vertical":
                self._paned.set_orientation(Gtk.Orientation.HORIZONTAL)
                if self._notebook2.get_n_pages() == 0:
                    self._notebook2.show()
                    self._add_new_tab(target_notebook=self._notebook2)
                else:
                    self._notebook2.show()
                self._split_single_act.set_active(False)
                self._split_v_act.set_active(True)
                self._split_h_act.set_active(False)
                w, _h = self.get_size()
                self._paned.set_position(max(200, w // 2))
            elif mode == "horizontal":
                self._paned.set_orientation(Gtk.Orientation.VERTICAL)
                if self._notebook2.get_n_pages() == 0:
                    self._notebook2.show()
                    self._add_new_tab(target_notebook=self._notebook2)
                else:
                    self._notebook2.show()
                self._split_single_act.set_active(False)
                self._split_v_act.set_active(False)
                self._split_h_act.set_active(True)
                _w, h = self.get_size()
                self._paned.set_position(max(100, h // 2))

            self._update_tabs_menu()
        finally:
            self._splitting = False

    def _move_tab_between(self, src, dst, idx):
        if idx < 0 or idx >= src.get_n_pages():
            return
        page = src.get_nth_page(idx)
        title = self._get_tab_text(page)
        src.remove_page(idx)
        lbl_box, lbl = self._make_tab_label(
            title, lambda t=page: self._close_tab(t), term=page)
        self._tab_labels[page] = (lbl_box, lbl)
        self._widget_nb_map[page] = dst
        dst.append_page(page, lbl_box)
        dst.set_tab_reorderable(page, True)
        dst.show_all()
        dst.set_current_page(dst.get_n_pages() - 1)
        if src is self._notebook2 and src.get_n_pages() == 0:
            self._set_split("single")
        if src is self._notebook and src.get_n_pages() == 0:
            self._notebook.set_show_tabs(False)

    def _focus_other_pane(self):
        if self._split_mode == "single":
            return
        focus = self.get_focus()
        target = self._notebook2
        current = self._notebook
        if focus:
            p = focus.get_parent()
            while p:
                if p is self._notebook2:
                    target, current = self._notebook, self._notebook2
                    break
                if p is self._notebook:
                    break
                p = p.get_parent() if hasattr(p, 'get_parent') else None
        if target.get_n_pages() > 0:
            idx = target.get_current_page()
            page = target.get_nth_page(idx)
            page._vte.grab_focus()

    # ── Header bar ───────────────────────────────────────────

    def _build_headerbar(self):
        from tpgk.icons import icon_button, split_view_image

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title(self.get_title())
        self._headerbar = header

        self._toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)

        new_tab_btn = icon_button("tab-new-symbolic", tooltip="Open a new terminal tab (Ctrl+Shift+T)")
        new_tab_btn.connect("clicked", lambda *a: self._on_new_tab())
        self._toolbar.pack_start(new_tab_btn, False, False, 0)

        new_win_btn = icon_button("window-new-symbolic", tooltip="Open a new terminal window (Ctrl+Shift+N)")
        new_win_btn.connect("clicked", lambda *a: self._on_new_window())
        self._toolbar.pack_start(new_win_btn, False, False, 0)

        self._toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        split_v_btn = icon_button(custom_image=split_view_image(True),
                                   tooltip="Split vertically – left/right panels (Ctrl+Shift+E)")
        split_v_btn.connect("clicked", lambda *a: self._set_split(
            "single" if self._split_mode == "vertical" else "vertical"))
        self._toolbar.pack_start(split_v_btn, False, False, 0)

        split_h_btn = icon_button(custom_image=split_view_image(False),
                                   tooltip="Split horizontally – top/bottom panels (Ctrl+Shift+D)")
        split_h_btn.connect("clicked", lambda *a: self._set_split(
            "single" if self._split_mode == "horizontal" else "horizontal"))
        self._toolbar.pack_start(split_h_btn, False, False, 0)

        self._toolbar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 4)

        copy_btn = icon_button("edit-copy-symbolic", tooltip="Copy selected text (Ctrl+Shift+C)")
        copy_btn.connect("clicked", lambda *a: self._term_copy())
        self._toolbar.pack_start(copy_btn, False, False, 0)

        paste_btn = icon_button("edit-paste-symbolic", tooltip="Paste from clipboard (Ctrl+Shift+V)")
        paste_btn.connect("clicked", lambda *a: self._term_paste())
        self._toolbar.pack_start(paste_btn, False, False, 0)

        header.pack_start(self._toolbar)

        self._menubar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._menubar.get_style_context().add_class("tpgk-menu-row")
        self._menu_buttons = []
        for lbl in ("File", "Edit", "View", "Terminal", "Tabs", "Help"):
            btn = Gtk.MenuButton(label=lbl)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            self._menubar.pack_start(btn, False, False, 0)
            self._menu_buttons.append(btn)

        self._tab_list_btn = self._make_tab_list_button()
        header.pack_end(self._tab_list_btn)

        self.set_titlebar(header)

    # ── Tab management ───────────────────────────────────────

    def _add_new_tab(self, cwd=None, target_notebook=None):
        term = TerminalBox(self)

        base_name = self._settings.get("tab_title", "Terminal")
        base_title = f"{base_name} {self._next_tab_number}"
        self._next_tab_number += 1
        self._tab_base_titles[term] = base_title

        nb = target_notebook or self._active_notebook()

        lbl_box, lbl = self._make_tab_label(
            base_title, lambda t=term: self._close_tab(t), term=term)
        self._tab_labels[term] = (lbl_box, lbl)
        self._widget_nb_map[term] = nb

        idx = nb.append_page(term, lbl_box)
        nb.set_tab_reorderable(term, True)
        nb.set_show_tabs(True)
        nb.show_all()
        nb.set_current_page(idx)
        self._update_tabs_menu()

        term.launch(cwd)
        term.show_all()
        GLib.idle_add(term._vte.grab_focus)

    def _make_tab_label(self, name, on_close, term=None):
        eb = Gtk.EventBox()
        eb.connect("button-press-event", self._on_tab_button_press)
        eb._term = term
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        lbl = Gtk.Label(label=name)
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_tooltip_text("Close tab")
        btn.add(Gtk.Image.new_from_icon_name("window-close-symbolic",
                                             Gtk.IconSize.MENU))
        btn.connect("clicked", lambda _b: on_close())
        box.pack_start(lbl, True, True, 0)
        box.pack_start(btn, False, False, 0)
        eb.add(box)
        eb.show_all()
        return eb, lbl

    def _on_tab_button_press(self, widget, event):
        if event.button != 3:
            return False
        term = getattr(widget, '_term', None)
        if term is None:
            return False
        menu = Gtk.Menu()

        item_close = Gtk.MenuItem(label="Close Tab")
        item_close.connect("activate", lambda *a, t=term: self._close_tab(t))
        menu.append(item_close)

        item_detach = Gtk.MenuItem(label="Detach Tab")
        item_detach.connect("activate", lambda *a, t=term: self._detach_tab(t))
        menu.append(item_detach)

        menu.append(Gtk.SeparatorMenuItem())

        item_copy = Gtk.MenuItem(label="Copy All Text")
        item_copy.connect("activate", lambda *a, t=term: t.select_all())
        menu.append(item_copy)

        item_copy_notes = Gtk.MenuItem(label="Copy All to Notes")
        item_copy_notes.connect("activate", lambda *a, t=term: self._copy_all_to_notes(t))
        menu.append(item_copy_notes)

        menu.append(Gtk.SeparatorMenuItem())

        item_v = Gtk.MenuItem(label="Move to Vertical Split")
        item_v.connect("activate", lambda *a, t=term: self._move_tab_to_split(t, "vertical"))
        item_h = Gtk.MenuItem(label="Move to Horizontal Split")
        item_h.connect("activate", lambda *a, t=term: self._move_tab_to_split(t, "horizontal"))
        menu.append(item_v)
        menu.append(item_h)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _move_tab_to_split(self, term, mode):
        if term is None:
            return
        src_nb, src_idx = self._find_terminal(term)
        if src_idx < 0:
            return
        total = self._notebook.get_n_pages() + self._notebook2.get_n_pages()
        if total < 2:
            self._set_split(mode)
            return
        if src_nb is self._notebook2:
            self._move_tab_between(self._notebook2, self._notebook, src_idx)
            self._set_split(mode)
        else:
            self._move_tab_between(self._notebook, self._notebook2, src_idx)
            self._set_split(mode)

    def _close_tab(self, term=None):
        if term is None:
            term = self._current_terminal()
        if term is None:
            return
        nb, idx = self._find_terminal(term)
        if idx >= 0:
            term.terminate()
            self._tab_labels.pop(term, None)
            self._tab_base_titles.pop(term, None)
            self._widget_nb_map.pop(term, None)
            nb.remove_page(idx)
            self._update_tabs_menu()

    def _on_page_removed(self):
        if self._notebook.get_n_pages() == 0 and self._notebook2.get_n_pages() == 0:
            self.destroy()
        elif self._notebook2.get_n_pages() == 0 and self._split_mode != "single":
            self._set_split("single")

    def _set_tab_text(self, term, text):
        entry = self._tab_labels.get(term)
        if entry:
            _, lbl = entry
            lbl.set_text(text)

    def _get_tab_text(self, term):
        entry = self._tab_labels.get(term)
        if entry:
            _, lbl = entry
            return lbl.get_text()
        return ""

    def set_tab_title_from_terminal(self, term, title):
        base = self._tab_base_titles.get(term, self._settings.get("tab_title", "Terminal"))
        mode = self._settings.get("dynamic_title", "replace")

        # Extract progressive number from base title (e.g. "Terminal 3" -> "3")
        num = base.split()[-1] if base else ""
        if not num.isdigit():
            num = ""

        if mode == "replace":
            display = f"{num}. {title}" if num else title
        elif mode == "before":
            display = f"{num}. {title} | {base}" if num else f"{title} | {base}"
        elif mode == "after":
            display = f"{num}. {base} | {title}" if num else f"{base} | {title}"
        else:
            display = base

        self._set_tab_text(term, display)

        if self._total_tabs() == 1:
            self.set_title(f"TPGK - {title}")

    def _update_tabs_menu(self):
        self._populate_tab_menu(self._tabs_menu)

    def _populate_tab_menu(self, menu):
        for child in menu.get_children():
            menu.remove(child)

        idx = 0
        for nb in (self._notebook, self._notebook2):
            cur = self._current_pages.get(nb, nb.get_current_page())
            cur_page = nb.get_nth_page(cur) if cur >= 0 and cur < nb.get_n_pages() else None
            for i in range(nb.get_n_pages()):
                page = nb.get_nth_page(i)
                text = self._get_tab_text(page)
                label = f"{idx+1}. {text}"
                if nb is self._notebook2:
                    label = f"[R] {label}"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda *a, n=nb, p=i: self._jump_to_tab(n, p))
                if page is cur_page:
                    item.set_sensitive(False)
                menu.append(item)
                item.show()
                idx += 1

        if idx == 0:
            item = Gtk.MenuItem(label="(no tabs)")
            item.set_sensitive(False)
            menu.append(item)
            item.show()

    def _make_tab_list_button(self):
        """Chevron button pinned at the end of a tab strip, so all open tabs
        stay one click away even once the strip overflows and scrolls.

        Given a left margin and a comfortable minimum size so it never sits
        flush against GtkNotebook's own scroll arrows (which otherwise makes
        the two nearly-touching, same-size arrows hard to tell apart and
        click accurately).
        """
        btn = Gtk.MenuButton()
        from tpgk.icons import symbolic_image
        btn.set_image(symbolic_image("pan-down-symbolic", 16))
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_size_request(32, 32)
        btn.set_margin_start(8)
        btn.set_tooltip_text("Show all open tabs")
        menu = Gtk.Menu()
        menu.get_style_context().add_class("tpgk-tab-menu")
        menu.set_reserve_toggle_size(False)
        btn.set_popup(menu)
        btn.connect("toggled", lambda b: self._populate_tab_menu(menu) if b.get_active() else None)
        return btn

    def _jump_to_tab(self, nb, page_idx):
        nb.set_current_page(page_idx)
        nb.show_all()
        page = nb.get_nth_page(page_idx)
        if page:
            page._vte.grab_focus()

    def _on_switch_tab(self, notebook, page, page_num):
        self._current_pages[notebook] = page_num
        if page:
            GLib.idle_add(page._vte.grab_focus)
            if hasattr(self, '_read_only_action'):
                self._read_only_action.set_active(not page._vte.get_input_enabled())
        self._update_tabs_menu()
        GLib.idle_add(self._apply_tab_colors)

    # ── Menu callbacks ───────────────────────────────────────

    def _on_new_tab(self, *a):
        self._add_new_tab()

    def _on_new_window(self, *a):
        env = os.environ.copy()
        env["TPGK_RELOAD_MODULES"] = "1"
        subprocess.Popen([sys.executable, "-m", "tpgk"], env=env, start_new_session=True)

    def _on_open_fm(self, *a):
        fm = _detect_file_manager(self._settings)
        if not fm:
            dialog = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL,
                                       Gtk.MessageType.WARNING, Gtk.ButtonsType.OK,
                                       "No file manager found.")
            dialog.run()
            dialog.destroy()
            return
        term = self._current_terminal()
        cwd = term.get_cwd() if term else os.path.expanduser("~")
        subprocess.Popen([fm, cwd], start_new_session=True)

    def _term_copy(self, *a):
        term = self._current_terminal()
        if term:
            term.copy()

    def _term_paste(self, *a):
        term = self._current_terminal()
        if term:
            term.paste()

    def _term_paste_sel(self, *a):
        term = self._current_terminal()
        if term:
            term.paste_selection()

    def _term_select_all(self, *a):
        term = self._current_terminal()
        if term:
            term.select_all()

    def _open_settings(self, *a):
        from tpgk.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        dialog.run()
        dialog.destroy()

    def _on_toggle_show_tabs(self, check):
        self._settings.set("show_tabs", check.get_active())
        self._notebook.set_show_tabs(check.get_active())
        self._notebook2.set_show_tabs(check.get_active())

    def _on_toggle_show_menubar(self, check):
        self._settings.set("show_menubar", check.get_active())
        self._menubar.set_visible(check.get_active())

    def _on_toggle_show_scrollbar(self, check):
        pos = "right" if check.get_active() else "disabled"
        self._settings.set("scrollbar_position", pos)
        for nb in (self._notebook, self._notebook2):
            for i in range(nb.get_n_pages()):
                page = nb.get_nth_page(i)
                page.set_scrollbar_visible(check.get_active())

    def _on_toggle_show_toolbar(self, check):
        self._settings.set("show_toolbar", check.get_active())
        self._toolbar.set_visible(check.get_active())

    def _on_toggle_show_stats(self, check):
        self._settings.set("show_stats", check.get_active())
        self._apply_stats_visibility()

    def _apply_stats_visibility(self):
        visible = self._settings.get("show_stats", False)
        self._stats_label.set_visible(visible)
        if visible:
            self._start_stats_timer()
        else:
            self._stop_stats_timer()

    def _start_stats_timer(self):
        if self._stats_source_id:
            return
        self._refresh_stats()
        self._stats_source_id = GLib.timeout_add_seconds(3, self._refresh_stats)

    def _stop_stats_timer(self):
        if self._stats_source_id:
            GLib.source_remove(self._stats_source_id)
            self._stats_source_id = 0

    def _refresh_stats(self):
        from tpgk.system_stats import collect
        term = self._current_terminal()
        is_ssh = term.is_ssh() if term else False
        stats = collect(is_ssh)
        self._stats_label.set_text(stats)
        return True

    def _toggle_fullscreen(self, *a):
        if self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _zoom_in(self, *a):
        for nb in (self._notebook, self._notebook2):
            for i in range(nb.get_n_pages()):
                nb.get_nth_page(i).zoom_in()

    def _zoom_out(self, *a):
        for nb in (self._notebook, self._notebook2):
            for i in range(nb.get_n_pages()):
                nb.get_nth_page(i).zoom_out()

    def _zoom_reset(self, *a):
        for nb in (self._notebook, self._notebook2):
            for i in range(nb.get_n_pages()):
                nb.get_nth_page(i).zoom_reset()

    def _set_title_dialog(self, *a):
        dialog = Gtk.Dialog(title="Set Tab Title", transient_for=self,
                            modal=True, destroy_with_parent=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Set", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        term = self._current_terminal()
        if term:
            entry.set_text(self._get_tab_text(term))
        dialog.get_content_area().pack_start(entry, True, True, 8)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            title = entry.get_text().strip()
            if title:
                self.set_title(f"TPGK - {title}")
                if term:
                    self._set_tab_text(term, title)
                    self._tab_base_titles[term] = title
        dialog.destroy()

    def _set_encoding(self, encoding: str):
        term = self._current_terminal()
        if term:
            term.set_encoding(encoding)
            text = self._get_tab_text(term).split(" [")[0]
            self._set_tab_text(term, f"{text} [{encoding}]")
            self._settings.set("encoding", encoding)
        for action, enc_name in self._encoding_actions:
            action.set_active(enc_name == encoding)

    def _send_signal(self, sig: int):
        term = self._current_terminal()
        if term:
            term.kill(sig)

    def _reset_terminal(self, *a):
        term = self._current_terminal()
        if term:
            term.reset(clear=False)

    def _reset_and_clear(self, *a):
        term = self._current_terminal()
        if term:
            term.reset(clear=True)

    def _on_toggle_read_only(self, check):
        term = self._current_terminal()
        if term:
            term.set_read_only(check.get_active())

    def _prev_tab(self, *a):
        focus = self.get_focus()
        nb = self._notebook
        if focus:
            p = focus.get_parent()
            while p:
                if p is self._notebook2:
                    nb = self._notebook2; break
                if p is self._notebook:
                    break
                p = p.get_parent() if hasattr(p, 'get_parent') else None
        n = nb.get_n_pages()
        if n > 1:
            idx = nb.get_current_page()
            nb.set_current_page((idx - 1) % n)

    def _next_tab(self, *a):
        focus = self.get_focus()
        nb = self._notebook
        if focus:
            p = focus.get_parent()
            while p:
                if p is self._notebook2:
                    nb = self._notebook2; break
                if p is self._notebook:
                    break
                p = p.get_parent() if hasattr(p, 'get_parent') else None
        n = nb.get_n_pages()
        if n > 1:
            idx = nb.get_current_page()
            nb.set_current_page((idx + 1) % n)

    def _move_tab(self, delta):
        focus = self.get_focus()
        nb = self._notebook
        if focus:
            p = focus.get_parent()
            while p:
                if p is self._notebook2:
                    nb = self._notebook2; break
                if p is self._notebook:
                    break
                p = p.get_parent() if hasattr(p, 'get_parent') else None
        n = nb.get_n_pages()
        idx = nb.get_current_page()
        new_idx = idx + delta
        if 0 <= new_idx < n:
            page = nb.get_nth_page(idx)
            nb.reorder_child(page, new_idx)
            self._update_tabs_menu()

    def _detach_tab(self, term=None, *a):
        if term is None:
            term = self._current_terminal()
        if not term:
            return
        nb, idx = self._find_terminal(term)
        title = self._get_tab_text(term)
        nb.remove_page(idx)
        self._tab_labels.pop(term, None)
        self._tab_base_titles.pop(term, None)
        self._widget_nb_map.pop(term, None)
        self._update_tabs_menu()

        new_win = _DetachedWindow(term, title)
        # Fix #4a: update terminal's back-reference so Ctrl+Shift shortcuts target the new window
        term._window = new_win
        # Fix #4b: register with the Gtk.Application so the main loop stays alive for this window
        app = self.get_application()
        if app:
            app.add_window(new_win)
        new_win.connect("destroy", lambda w: term.terminate())
        new_win.show_all()
        GLib.idle_add(term._vte.grab_focus)

    def _copy_all_to_notes(self, term):
        text = term._vte.get_text_format(Vte.Format.TEXT)
        if text:
            path = term._notes.write_note(text)
            term._vte.feed(
                f"\r\n\x1b[32m+ Added all text to note: {path}\x1b[0m\r\n".encode()
            )
            term._vte.feed_child(b'\r')

    def _show_about(self, *a):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("TPGK")
        dialog.set_version("1.1.0")
        dialog.set_comments(
            "Advanced terminal emulator powered by VTE\n"
            "Supports tmux-like splits (View > Split)\n\n"
            "Features:\n"
            "- Full terminal emulation (VTE/xterm-256color)\n"
            "- Command history with interactive search (Ctrl+R)\n"
            "- AI chat (OpenAI, Claude, Gemini, DeepSeek, Ollama, Custom)\n"
            "- /history, /ai, /connect, /wnotes, /onotes\n"
            "- Tab autocompletion for TPGK commands\n"
            "- Tabs with detach, move, reorder\n"
            "- 16-color palette editor with presets\n"
            "- Full menu bar, toolbar, scrollbar\n"
            "- Send signals, Set encoding, File manager integration"
        )
        dialog.set_copyright("Andres Zanzani")
        dialog.set_license_type(Gtk.License.CUSTOM)
        dialog.set_license(EUPL_LICENSE_TEXT)
        dialog.run()
        dialog.destroy()

    # ── Window signals ───────────────────────────────────────

    def _on_close(self, *a):
        if self._settings.get("confirm_close", True):
            dialog = Gtk.MessageDialog(
                self, Gtk.DialogFlags.MODAL,
                Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO,
                "Close all tabs and exit?"
            )
            resp = dialog.run()
            dialog.destroy()
            if resp != Gtk.ResponseType.YES:
                return True

        for nb in (self._notebook, self._notebook2):
            for i in range(nb.get_n_pages() - 1, -1, -1):
                nb.get_nth_page(i).terminate()
        self.destroy()

    def _on_window_key(self, widget, event):
        state = event.state
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        key = event.keyval

        if ctrl and key == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        if key == Gdk.KEY_F11:
            self._toggle_fullscreen()
            return True
        return False

    # ── Public signals for TerminalBox ───────────────────────

    def new_tab_signal(self):
        self._add_new_tab()

    def close_tab_signal(self):
        self._close_tab()

    def close_window_signal(self):
        self._on_close()

    def set_title_dialog(self):
        self._set_title_dialog()

    def reset_terminal(self):
        self._reset_terminal()

    def reset_and_clear(self):
        self._reset_and_clear()

    def split_signal(self, mode):
        current = self._split_mode
        if current == mode:
            self._set_split("single")
        else:
            self._set_split(mode)

    def focus_other_pane_signal(self):
        if self._split_mode != "single":
            self._focus_other_pane()
