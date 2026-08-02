import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from tpgk.settings import Settings, COLOR_SCHEMES, COLOR_PALETTES


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent=None):
        super().__init__(title="Preferences - TPGK", transient_for=parent,
                         modal=True, destroy_with_parent=True)
        self.set_default_size(880, 700)
        self._settings = Settings()

        self._palette_btns = {}
        self._fg_color_btn = None
        self._bg_color_btn = None
        self._cursor_color_btn = None
        self._highlight_btn = None
        self._highlight_bg_btn = None

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)

        self._sidebar = Gtk.StackSidebar()
        self._sidebar.set_stack(self._stack)
        self._sidebar.set_size_request(160, -1)

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        content_box.pack_start(self._sidebar, False, False, 0)
        content_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        content_box.pack_start(self._stack, True, True, 0)
        self.get_content_area().pack_start(content_box, True, True, 8)

        self._stack.add_titled(self._build_general(), "general", "General")
        self._stack.add_titled(self._build_appearance(), "appearance", "Appearance")
        self._stack.add_titled(self._build_colors(), "colors", "Colors")
        self._stack.add_titled(self._build_compatibility(), "compatibility", "Compatibility")
        self._stack.add_titled(self._build_ai(), "ai", "AI")
        self._stack.add_titled(self._build_notes(), "notes", "Notes")

        # Slightly larger text/controls throughout the dialog for readability
        # (users with reduced or age-related farsighted vision benefit most
        # from the sidebar categories and entry fields being easy to read).
        readability_css = Gtk.CssProvider()
        readability_css.load_from_data(b"""
            stacksidebar row { padding: 8px 10px; }
            stacksidebar row label { font-size: 1.05em; }
            entry, spinbutton, combobox button, checkbutton label,
            radiobutton label { font-size: 1.03em; }
            entry, spinbutton { padding: 4px 6px; }
        """)
        self.get_style_context().add_provider(
            readability_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok_btn = self.add_button("OK", Gtk.ResponseType.OK)
        ok_btn.get_style_context().add_class("suggested-action")
        self.connect("response", self._on_response)

        self.show_all()

    def _section(self, grid, row, title):
        label = Gtk.Label(label=f"<b>{title}</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, row, 2, 1)
        return row + 1

    def _row(self, grid, row, label_text, widget):
        lbl = Gtk.Label(label=label_text)
        lbl.set_halign(Gtk.Align.END)
        lbl.set_margin_end(8)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return row + 1

    def _make_color_button(self, hex_color: str, tooltip: str = "") -> Gtk.ColorButton:
        rgba = _hex_to_rgba(hex_color)
        btn = Gtk.ColorButton.new_with_rgba(rgba)
        btn.set_size_request(48, 22)
        btn.set_halign(Gtk.Align.START)
        btn._hex = hex_color
        btn.connect("color-set", self._on_color_set)
        if tooltip:
            btn.set_tooltip_text(tooltip)
        return btn

    def _update_btn_color(self, btn, hex_color: str):
        rgba = _hex_to_rgba(hex_color)
        btn.set_rgba(rgba)
        btn._hex = hex_color

    def _on_color_set(self, btn):
        rgba = btn.get_rgba()
        btn._hex = _rgba_to_hex(rgba)

    def _build_general(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        grid = Gtk.Grid()
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)
        grid.set_row_spacing(9)
        grid.set_column_spacing(12)
        row = 0

        row = self._section(grid, row, "Title")
        self._entry_title = Gtk.Entry()
        self._entry_title.set_text(self._settings.get("tab_title", "Terminal"))
        self._entry_title.set_tooltip_text("Default name displayed on each new tab")
        row = self._row(grid, row, "Initial title:", self._entry_title)

        self._combo_dynamic = Gtk.ComboBoxText()
        self._combo_dynamic.append_text("Replace initial title")
        self._combo_dynamic.append_text("Goes before initial title")
        self._combo_dynamic.append_text("Goes after initial title")
        self._combo_dynamic.append_text("Isn't displayed")
        dyn_map = {"replace": 0, "before": 1, "after": 2, "hide": 3}
        self._combo_dynamic.set_active(dyn_map.get(
            self._settings.get("dynamic_title", "replace"), 0))
        self._combo_dynamic.set_tooltip_text(
            "How to combine a title set by the shell (OSC escape) with the initial title:\n"
            "- Replace: use only the shell title\n"
            "- Before: shell title | initial title\n"
            "- After: initial title | shell title\n"
            "- Hide: always show the initial title"
        )
        row = self._row(grid, row, "Dynamic title:", self._combo_dynamic)

        row += 1
        row = self._section(grid, row, "Command")
        self._chk_login = Gtk.CheckButton(label="Run as login shell")
        self._chk_login.set_active(self._settings.get("login_shell", True))
        self._chk_login.set_tooltip_text("Start the shell as a login shell (loads .profile / .bash_profile)")
        row = self._row(grid, row, "Login shell:", self._chk_login)

        self._entry_shell = Gtk.Entry()
        self._entry_shell.set_text(self._settings.get("shell_command", "/bin/bash"))
        self._entry_shell.set_tooltip_text("Custom shell command or path. Use $SHELL for the default shell")
        row = self._row(grid, row, "Shell:", self._entry_shell)

        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._spin_columns = Gtk.SpinButton.new_with_range(40, 300, 1)
        self._spin_columns.set_value(self._settings.get("terminal_columns", 80))
        self._spin_columns.set_tooltip_text("Default terminal width in character columns (40-300)")
        self._spin_rows = Gtk.SpinButton.new_with_range(10, 120, 1)
        self._spin_rows.set_value(self._settings.get("terminal_rows", 24))
        self._spin_rows.set_tooltip_text("Default terminal height in character rows (10-120)")
        size_box.pack_start(self._spin_columns, False, False, 0)
        size_box.pack_start(Gtk.Label(label="x"), False, False, 2)
        size_box.pack_start(self._spin_rows, False, False, 0)
        size_box.pack_start(Gtk.Label(label="(cols x rows)"), False, False, 6)
        row = self._row(grid, row, "Size:", size_box)

        row += 1
        row = self._section(grid, row, "Scrolling")
        self._combo_scrollbar_pos = Gtk.ComboBoxText()
        self._combo_scrollbar_pos.append_text("Right side")
        self._combo_scrollbar_pos.append_text("Left side")
        self._combo_scrollbar_pos.append_text("Disabled")
        pos_map = {"right": 0, "left": 1, "disabled": 2}
        self._combo_scrollbar_pos.set_active(
            pos_map.get(self._settings.get("scrollbar_position", "right"), 0)
        )
        self._combo_scrollbar_pos.set_tooltip_text("Position of the scrollbar or disable it entirely")
        row = self._row(grid, row, "Scrollbar is:", self._combo_scrollbar_pos)

        self._chk_scrollback_unlimited = Gtk.CheckButton()
        self._chk_scrollback_unlimited.set_active(
            self._settings.get("scrollback_lines", 10000) == -1)
        self._chk_scrollback_unlimited.set_tooltip_text("Unlimited scrollback buffer")
        self._chk_scrollback_unlimited.connect("toggled", self._on_unlimited_toggled)
        row = self._row(grid, row, "Unlimited scrollback:", self._chk_scrollback_unlimited)

        self._spin_scrollback = Gtk.SpinButton.new_with_range(500, 100000, 500)
        if self._settings.get("scrollback_lines", 10000) > 0:
            self._spin_scrollback.set_value(self._settings.get("scrollback_lines", 10000))
        else:
            self._spin_scrollback.set_value(10000)
        self._spin_scrollback.set_sensitive(
            self._settings.get("scrollback_lines", 10000) > 0)
        self._spin_scrollback.set_tooltip_text("Maximum number of lines kept in the scrollback buffer")
        row = self._row(grid, row, "Scrollback lines:", self._spin_scrollback)

        self._chk_scroll_output = Gtk.CheckButton()
        self._chk_scroll_output.set_active(self._settings.get("scroll_on_output", True))
        self._chk_scroll_output.set_tooltip_text("Automatically scroll to the bottom when new output appears")
        row = self._row(grid, row, "Scroll on output:", self._chk_scroll_output)

        self._chk_scroll_keystroke = Gtk.CheckButton()
        self._chk_scroll_keystroke.set_active(self._settings.get("scroll_on_keystroke", True))
        self._chk_scroll_keystroke.set_tooltip_text("Automatically scroll to the bottom when typing")
        row = self._row(grid, row, "Scroll on keystroke:", self._chk_scroll_keystroke)

        row += 1
        row = self._section(grid, row, "Other")
        self._chk_confirm_close = Gtk.CheckButton()
        self._chk_confirm_close.set_active(self._settings.get("confirm_close", True))
        self._chk_confirm_close.set_tooltip_text("Ask for confirmation before closing the window")
        row = self._row(grid, row, "Confirm before closing:", self._chk_confirm_close)

        self._chk_auto_copy = Gtk.CheckButton()
        self._chk_auto_copy.set_active(self._settings.get("auto_copy_selection", True))
        self._chk_auto_copy.set_tooltip_text("Automatically copy selected text to the clipboard")
        row = self._row(grid, row, "Auto-copy selection:", self._chk_auto_copy)

        self._chk_warn_paste = Gtk.CheckButton()
        self._chk_warn_paste.set_active(self._settings.get("show_unsafe_paste_dialog", True))
        self._chk_warn_paste.set_tooltip_text("Warn before pasting multi-line text that may contain harmful commands")
        row = self._row(grid, row, "Warn multi-line paste:", self._chk_warn_paste)

        self._entry_fm = Gtk.Entry()
        self._entry_fm.set_text(self._settings.get("file_manager", ""))
        self._entry_fm.set_placeholder_text("auto-detect")
        self._entry_fm.set_tooltip_text("Override the file manager (e.g. nemo, thunar, dolphin). Leave blank to auto-detect")
        row = self._row(grid, row, "File manager:", self._entry_fm)

        row += 1
        row = self._section(grid, row, "Session")
        self._chk_session_restore = Gtk.CheckButton()
        self._chk_session_restore.set_active(self._settings.get("session_restore", True))
        self._chk_session_restore.set_tooltip_text("Restore tabs and splits from last session on startup")
        row = self._row(grid, row, "Restore last session:", self._chk_session_restore)

        self._chk_bell_notify = Gtk.CheckButton()
        self._chk_bell_notify.set_active(self._settings.get("bell_notification", False))
        self._chk_bell_notify.set_tooltip_text("Show desktop notification when a command completes (requires OSC 133 shell integration)")
        row = self._row(grid, row, "Notify on command completion:", self._chk_bell_notify)

        row += 1
        row = self._section(grid, row, "Keyboard Modes")
        self._chk_hint_mode = Gtk.CheckButton()
        self._chk_hint_mode.set_active(self._settings.get("hint_mode_enabled", True))
        self._chk_hint_mode.set_tooltip_text("Ctrl+Shift+H: highlight URLs, paths and git SHAs with keyboard-selectable labels")
        row = self._row(grid, row, "Hint mode:", self._chk_hint_mode)

        self._chk_vi_copy = Gtk.CheckButton()
        self._chk_vi_copy.set_active(self._settings.get("vi_copy_mode_enabled", False))
        self._chk_vi_copy.set_tooltip_text("Ctrl+Shift+Y: VI-style copy mode (hjkl scroll, v select, y yank, Esc exit)")
        row = self._row(grid, row, "VI copy mode:", self._chk_vi_copy)

        sw.add(grid)
        return sw

    def _build_appearance(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        grid = Gtk.Grid()
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)
        grid.set_row_spacing(9)
        grid.set_column_spacing(12)
        row = 0

        row = self._section(grid, row, "Font")
        font_desc = f"{self._settings.get('font_name', 'Monospace')} {self._settings.get('font_size', 12)}"
        self._font_btn = Gtk.FontButton()
        self._font_btn.set_font_name(font_desc)
        self._font_btn.set_tooltip_text("Choose a font family and size")
        row = self._row(grid, row, "Font:", self._font_btn)

        self._chk_bold = Gtk.CheckButton()
        self._chk_bold.set_active(self._settings.get("allow_bold_text", True))
        self._chk_bold.set_tooltip_text("Render bold text as bold. Disable for uniform text weight")
        row = self._row(grid, row, "Allow bold text:", self._chk_bold)

        row += 1
        row = self._section(grid, row, "Color Scheme")
        self._combo_scheme = Gtk.ComboBoxText()
        for name in COLOR_SCHEMES:
            self._combo_scheme.append_text(name)
        scheme = self._settings.get("color_scheme", "Dark (Default)")
        schemes = list(COLOR_SCHEMES.keys())
        if scheme in schemes:
            self._combo_scheme.set_active(schemes.index(scheme))
        else:
            self._combo_scheme.set_active(0)
        self._combo_scheme.set_tooltip_text("Choose a built-in color scheme. Customize individual colors below")
        self._combo_scheme.connect("changed", self._on_scheme_changed)
        row = self._row(grid, row, "Scheme:", self._combo_scheme)

        row += 1
        row = self._section(grid, row, "Individual Colors")
        self._fg_color_btn = self._make_color_button(
            self._settings.get_fg_color(),
            "Default text foreground color – click to change")
        self._bg_color_btn = self._make_color_button(
            self._settings.get_bg_color(),
            "Terminal background color – click to change")
        self._cursor_color_btn = self._make_color_button(
            self._settings.get("cursor_color", "#ffffff"),
            "Cursor color – click to change")
        self._highlight_btn = self._make_color_button(
            self._settings.get("highlight_color", "#ffffff"),
            "Selected text color – click to change")
        self._highlight_bg_btn = self._make_color_button(
            self._settings.get("highlight_bg_color", "#446688"),
            "Selection background color – click to change")

        color_grid = Gtk.Grid()
        color_grid.set_column_spacing(12)
        color_grid.set_row_spacing(4)
        color_grid.attach(Gtk.Label(label="Foreground:"), 0, 0, 1, 1)
        color_grid.attach(self._fg_color_btn, 1, 0, 1, 1)
        color_grid.attach(Gtk.Label(label="Background:"), 0, 1, 1, 1)
        color_grid.attach(self._bg_color_btn, 1, 1, 1, 1)
        color_grid.attach(Gtk.Label(label="Cursor:"), 0, 2, 1, 1)
        color_grid.attach(self._cursor_color_btn, 1, 2, 1, 1)
        color_grid.attach(Gtk.Label(label="Highlight text:"), 2, 0, 1, 1)
        color_grid.attach(self._highlight_btn, 3, 0, 1, 1)
        color_grid.attach(Gtk.Label(label="Highlight bg:"), 2, 1, 1, 1)
        color_grid.attach(self._highlight_bg_btn, 3, 1, 1, 1)
        row = self._row(grid, row, "", color_grid)

        row += 1
        row = self._section(grid, row, "Tab Colors")
        self._tab_title_color_btn = self._make_color_button(
            self._settings.get("tab_title_color", "#ffffff"),
            "Color for inactive tab titles – click to change")
        row = self._row(grid, row, "Tab title:", self._tab_title_color_btn)

        self._tab_active_color_btn = self._make_color_button(
            self._settings.get("tab_active_title_color", "#ffffff"),
            "Color for the active tab title – click to change")
        row = self._row(grid, row, "Active tab:", self._tab_active_color_btn)

        row += 1
        row = self._section(grid, row, "Cursor")
        self._combo_cursor_shape = Gtk.ComboBoxText()
        self._combo_cursor_shape.append_text("block")
        self._combo_cursor_shape.append_text("underline")
        self._combo_cursor_shape.append_text("ibeam")
        shape = self._settings.get("cursor_shape", "block")
        shapes = ["block", "underline", "ibeam"]
        self._combo_cursor_shape.set_active(shapes.index(shape) if shape in shapes else 0)
        self._combo_cursor_shape.set_tooltip_text("Cursor appearance: block (filled rectangle), underline (_), ibeam (|)")
        row = self._row(grid, row, "Cursor shape:", self._combo_cursor_shape)

        self._chk_cursor_blink = Gtk.CheckButton()
        self._chk_cursor_blink.set_active(self._settings.get("cursor_blink", True))
        self._chk_cursor_blink.set_tooltip_text("Make the cursor blink periodically")
        row = self._row(grid, row, "Cursor blinking:", self._chk_cursor_blink)

        row += 1
        row = self._section(grid, row, "Transparency")
        self._spin_opacity = Gtk.SpinButton.new_with_range(0.3, 1.0, 0.05)
        self._spin_opacity.set_value(self._settings.get("opacity", 1.0))
        self._spin_opacity.set_tooltip_text("Window opacity (1.0 = fully opaque, 0.3 = almost transparent)")
        row = self._row(grid, row, "Opacity:", self._spin_opacity)

        self._chk_transparency = Gtk.CheckButton()
        self._chk_transparency.set_active(self._settings.get("enable_transparency", False))
        self._chk_transparency.set_tooltip_text("Enable RGBA compositing transparency. Requires a compositor (e.g. picom, Wayland)")
        row = self._row(grid, row, "Enable transparency:", self._chk_transparency)

        row += 1
        row = self._section(grid, row, "Padding")
        pad_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._spin_pad_h = Gtk.SpinButton.new_with_range(0, 60, 1)
        self._spin_pad_h.set_value(self._settings.get("window_padding_horizontal", 2))
        self._spin_pad_h.set_tooltip_text("Horizontal padding inside the terminal window (pixels)")
        pad_box.pack_start(Gtk.Label(label="H:"), False, False, 0)
        pad_box.pack_start(self._spin_pad_h, False, False, 0)
        self._spin_pad_v = Gtk.SpinButton.new_with_range(0, 60, 1)
        self._spin_pad_v.set_value(self._settings.get("window_padding_vertical", 2))
        self._spin_pad_v.set_tooltip_text("Vertical padding inside the terminal window (pixels)")
        pad_box.pack_start(Gtk.Label(label="V:"), False, False, 0)
        pad_box.pack_start(self._spin_pad_v, False, False, 0)
        row = self._row(grid, row, "Border:", pad_box)

        row += 1
        row = self._section(grid, row, "Underlines")
        self._combo_undercurl = Gtk.ComboBoxText()
        for style in ("single", "double", "curly", "dashed", "dotted"):
            self._combo_undercurl.append_text(style)
        curl_style = self._settings.get("undercurl_style", "single")
        styles = ["single", "double", "curly", "dashed", "dotted"]
        self._combo_undercurl.set_active(styles.index(curl_style) if curl_style in styles else 0)
        self._combo_undercurl.set_tooltip_text("Style for underlined text (e.g. compiler errors, spelling). curly requires VTE >= 0.58")
        row = self._row(grid, row, "Underline style:", self._combo_undercurl)

        sw.add(grid)
        return sw

    def _on_scheme_changed(self, combo):
        name = combo.get_active_text()
        if not name:
            return
        scheme = COLOR_SCHEMES.get(name, COLOR_SCHEMES["Dark (Default)"])
        palette = COLOR_PALETTES.get(name, COLOR_PALETTES["Dark (Default)"])

        self._update_btn_color(self._fg_color_btn, scheme["foreground"])
        self._update_btn_color(self._bg_color_btn, scheme["background"])

        for key, btn in self._palette_btns.items():
            if key in palette:
                self._update_btn_color(btn, palette[key])

    def _build_colors(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(8)
        vbox.set_margin_bottom(8)

        label = Gtk.Label(label="<b>16-Color Palette</b>")
        label.set_use_markup(True)
        label.set_halign(Gtk.Align.START)
        label.set_tooltip_text(
            "Customize the 16 ANSI terminal colors (8 normal + 8 bright).\n"
            "Click any color swatch to change it. Changes are saved automatically on OK."
        )
        vbox.pack_start(label, False, False, 4)

        saved = self._settings.get("custom_palette")
        scheme = self._settings.get("color_scheme", "Dark (Default)")
        palette = saved if saved else COLOR_PALETTES.get(scheme, COLOR_PALETTES["Dark (Default)"])

        labels_16 = [
            ("Black", "Red", "Green", "Yellow"),
            ("Blue", "Magenta", "Cyan", "White"),
            ("B.Black", "B.Red", "B.Green", "B.Yellow"),
            ("B.Blue", "B.Magenta", "B.Cyan", "B.White"),
        ]
        keys_16 = [
            ("black", "red", "green", "yellow"),
            ("blue", "magenta", "cyan", "white"),
            ("brightblack", "brightred", "brightgreen", "brightyellow"),
            ("brightblue", "brightmagenta", "brightcyan", "brightwhite"),
        ]
        tooltips_16 = [
            ("Normal black", "Normal red", "Normal green", "Normal yellow"),
            ("Normal blue", "Normal magenta", "Normal cyan", "Normal white"),
            ("Bright black (gray)", "Bright red", "Bright green", "Bright yellow"),
            ("Bright blue", "Bright magenta", "Bright cyan", "Bright white"),
        ]

        palette_grid = Gtk.Grid()
        palette_grid.set_row_spacing(2)
        palette_grid.set_column_spacing(12)

        for row_idx in range(4):
            for col_idx in range(4):
                key = keys_16[row_idx][col_idx]
                name = labels_16[row_idx][col_idx]
                tip = tooltips_16[row_idx][col_idx]
                btn = self._make_color_button(palette.get(key, "#000000"), tip)
                btn.set_size_request(48, 22)
                self._palette_btns[key] = btn

                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                lbl = Gtk.Label(label=name)
                lbl.set_margin_start(4)
                cell.pack_start(lbl, False, False, 0)
                cell.pack_start(btn, False, False, 0)
                palette_grid.attach(cell, col_idx, row_idx, 1, 1)

        vbox.pack_start(palette_grid, False, False, 8)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        load_btn = Gtk.Button(label="Load Preset...")
        load_btn.set_tooltip_text("Load a built-in color palette preset (Dark, Light, Solarized, Gruvbox, Monokai, Nord)")
        load_btn.connect("clicked", self._load_palette_preset_dialog)
        save_btn = Gtk.Button(label="Save As Custom")
        save_btn.set_tooltip_text("Save the current palette as a custom palette in your preferences")
        save_btn.connect("clicked", lambda b: self._save_palette())
        reset_btn = Gtk.Button(label="Reset to Default")
        reset_btn.set_tooltip_text("Reset all palette colors to the default Dark scheme")
        reset_btn.connect("clicked", lambda b: self._reset_palette())
        btn_box.pack_start(load_btn, False, False, 0)
        btn_box.pack_start(save_btn, False, False, 0)
        btn_box.pack_start(reset_btn, False, False, 0)
        vbox.pack_start(btn_box, False, False, 0)

        vbox.set_tooltip_text(
            "The 16-color palette defines how ANSI color codes (0-15) are rendered.\n"
            "These colors are used by CLI tools, syntax highlighters, and TUIs."
        )

        sw.add(vbox)
        return sw

    def _load_palette_preset_dialog(self, btn):
        dialog = Gtk.Dialog(title="Load Palette", transient_for=self,
                            modal=True, destroy_with_parent=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        load_btn = dialog.add_button("Load", Gtk.ResponseType.OK)

        combo = Gtk.ComboBoxText()
        presets = ["Dark (Default)", "Light", "Solarized Dark", "Solarized Light",
                   "Monokai", "Gruvbox Dark", "Nord", "Matrix"]
        for p in presets:
            combo.append_text(p)
        combo.set_active(0)
        combo.set_tooltip_text("Select a preset palette to load. This will overwrite the current palette colors")
        dialog.get_content_area().pack_start(combo, True, True, 8)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            name = combo.get_active_text()
            presets_map = {
                "Dark (Default)": COLOR_PALETTES["Dark (Default)"],
                "Light": COLOR_PALETTES["Light"],
                "Solarized Dark": COLOR_PALETTES["Solarized Dark"],
                "Solarized Light": COLOR_PALETTES["Solarized Light"],
                "Monokai": COLOR_PALETTES["Monokai"],
                "Gruvbox Dark": COLOR_PALETTES["Gruvbox Dark"],
                "Nord": COLOR_PALETTES["Nord"],
                "Matrix": COLOR_PALETTES["Matrix"],
            }
            palette = presets_map.get(name, COLOR_PALETTES["Dark (Default)"])
            for key, btn in self._palette_btns.items():
                if key in palette:
                    self._update_btn_color(btn, palette[key])
        dialog.destroy()

    def _save_palette(self):
        dialog = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL,
                                   Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                                   "Set your colors in the palette fields above and click OK.\n"
                                   "The custom palette will be saved with your preferences.")
        dialog.run()
        dialog.destroy()

    def _reset_palette(self):
        palette = COLOR_PALETTES.get("Dark (Default)", COLOR_PALETTES["Dark (Default)"])
        for key, btn in self._palette_btns.items():
            if key in palette:
                self._update_btn_color(btn, palette[key])

    def _build_compatibility(self):
        grid = Gtk.Grid()
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)
        grid.set_row_spacing(9)
        grid.set_column_spacing(12)
        row = 0

        row = self._section(grid, row, "Keyboard")
        self._combo_backspace = Gtk.ComboBoxText()
        self._combo_backspace.append_text("Auto-detect")
        self._combo_backspace.append_text("ASCII DEL (127)")
        self._combo_backspace.append_text("Escape sequence")
        self._combo_backspace.append_text("Control-H (8)")
        bs_map = {"auto": 0, "ascii-del": 1, "escape-sequence": 2, "control-h": 3}
        self._combo_backspace.set_active(
            bs_map.get(self._settings.get("backspace_binding", "ascii-del"), 1))
        self._combo_backspace.set_tooltip_text(
            "The character sequence sent when Backspace is pressed.\n"
            "- Auto-detect: let the terminal decide\n"
            "- ASCII DEL (127): standard for most terminals\n"
            "- Escape sequence: \\x1b\\x7f\n"
            "- Control-H (8): legacy, used by some shells"
        )
        row = self._row(grid, row, "Backspace key:", self._combo_backspace)

        self._combo_delete = Gtk.ComboBoxText()
        self._combo_delete.append_text("Auto-detect")
        self._combo_delete.append_text("Escape sequence")
        self._combo_delete.append_text("ASCII DEL (127)")
        self._combo_delete.append_text("Control-H (8)")
        del_map = {"auto": 0, "escape-sequence": 1, "ascii-del": 2, "control-h": 3}
        self._combo_delete.set_active(
            del_map.get(self._settings.get("delete_binding", "escape-sequence"), 1))
        self._combo_delete.set_tooltip_text(
            "The character sequence sent when Delete is pressed.\n"
            "- Auto-detect: let the terminal decide\n"
            "- Escape sequence: \\x1b[3~ (standard)\n"
            "- ASCII DEL (127): alternative\n"
            "- Control-H (8): legacy"
        )
        row = self._row(grid, row, "Delete key:", self._combo_delete)

        row += 1
        row = self._section(grid, row, "Encoding")
        self._combo_encoding = Gtk.ComboBoxText()
        encodings = ["UTF-8", "ISO-8859-1", "ISO-8859-15", "UTF-16",
                     "UTF-16BE", "UTF-16LE",
                     "CP1252", "CP850", "ASCII", "KOI8-R", "Shift_JIS", "EUC-JP", "GBK"]
        for enc in encodings:
            self._combo_encoding.append_text(enc)
        cur_enc = self._settings.get("encoding", "UTF-8")
        if cur_enc in encodings:
            self._combo_encoding.set_active(encodings.index(cur_enc))
        else:
            self._combo_encoding.set_active(0)
        self._combo_encoding.set_tooltip_text(
            "Default character encoding for new terminal tabs.\n"
            "Most users should keep this on UTF-8."
        )
        row = self._row(grid, row, "Default encoding:", self._combo_encoding)

        row += 1
        row = self._section(grid, row, "Integration")
        self._chk_osc133 = Gtk.CheckButton(label="Enable shell integration (OSC 133)")
        self._chk_osc133.set_active(self._settings.get("osc133", False))
        self._chk_osc133.set_tooltip_text(
            "Enables OSC 133 escape sequences for shell integration (bash/zsh).\n"
            "When active, TPGK writes a helper script to ~/.config/tpgk/osc133.sh\n"
            "and sets TPGK_SHELL_INTEGRATION=1. Requires sourcing the script in your\n"
            "~/.bashrc: [ -f ~/.config/tpgk/osc133.sh ] && source ~/.config/tpgk/osc133.sh"
        )
        row = self._row(grid, row, "OSC 133:", self._chk_osc133)

        row += 1
        reset_btn = Gtk.Button(label="Reset Compatibility Options to Defaults")
        reset_btn.set_tooltip_text("Reset backspace/delete bindings, encoding, and OSC 133 to their default values")
        reset_btn.connect("clicked", lambda *a: self._reset_compatibility())
        grid.attach(reset_btn, 0, row, 2, 1)
        row += 1

        return grid

    def _on_unlimited_toggled(self, check):
        self._spin_scrollback.set_sensitive(not check.get_active())

    def _reset_compatibility(self):
        self._combo_backspace.set_active(1)
        self._combo_delete.set_active(1)
        self._combo_encoding.set_active(0)
        self._chk_osc133.set_active(False)

    def _build_ai(self):
        grid = Gtk.Grid()
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)
        grid.set_row_spacing(9)
        grid.set_column_spacing(12)

        keys = self._settings.get("ai_keys", {})
        models = self._settings.get("ai_models", {})
        urls = self._settings.get("ai_urls", {})
        sys_prompts = self._settings.get("ai_system_prompts", {})

        providers = ["openai", "claude", "gemini", "deepseek", "ollama", "custom"]
        provider_tooltips = {
            "openai": "OpenAI API (gpt-4o, gpt-4-turbo, etc.). Requires an API key from https://platform.openai.com",
            "claude": "Anthropic Claude API. Requires an API key from https://console.anthropic.com",
            "gemini": "Google Gemini API. Requires an API key from https://aistudio.google.com",
            "deepseek": "DeepSeek API. Requires an API key from https://platform.deepseek.com",
            "ollama": "Local Ollama instance. No API key needed. Models are auto-detected via /api/tags",
            "custom": "Custom OpenAI-compatible API endpoint (llama.cpp, vLLM, LM Studio, etc.)",
        }
        self._ai_entries = {}
        row = 0

        for provider in providers:
            title = provider.title()
            row = self._section(grid, row, title)

            key_entry = Gtk.Entry()
            key_entry.set_text(keys.get(provider, ""))
            if provider not in ("ollama", "custom"):
                key_entry.set_visibility(False)
            key_entry.set_placeholder_text(f"{provider.upper()}_API_KEY" if provider not in ("ollama", "custom") else "(optional)")
            key_entry.set_tooltip_text(
                f"API key for {title}. "
                + (f"Set to your {title} API key." if provider not in ("ollama", "custom")
                   else "Optional: only needed if your server requires authentication.")
            )
            row = self._row(grid, row, "API Key:", key_entry)

            model_entry = Gtk.Entry()
            model_entry.set_text(models.get(provider, ""))
            model_entry.set_placeholder_text("default model")
            model_entry.set_tooltip_text(
                f"Model name override for {title}. Leave blank to use the default model.\n"
                + (f"With /connect, TPGK will auto-detect available models." if provider in ("ollama", "custom") else "")
            )
            row = self._row(grid, row, "Model:", model_entry)

            sys_prompt_buf = Gtk.TextBuffer()
            sys_prompt_buf.set_text(sys_prompts.get(provider, ""))
            sys_prompt_view = Gtk.TextView.new_with_buffer(sys_prompt_buf)
            sys_prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            sys_prompt_view.set_size_request(-1, 60)
            sys_prompt_scroll = Gtk.ScrolledWindow()
            sys_prompt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            sys_prompt_scroll.set_min_content_height(40)
            sys_prompt_scroll.add(sys_prompt_view)
            sys_prompt_scroll.set_tooltip_text(
                f"System prompt for {title}. Defines the AI assistant's persona and behavior.\n"
                "Leave blank for no system prompt."
            )
            sys_prompt_frame = Gtk.Frame()
            sys_prompt_frame.set_shadow_type(Gtk.ShadowType.IN)
            sys_prompt_frame.add(sys_prompt_scroll)
            lbl = Gtk.Label(label="Sys. prompt:")
            lbl.set_halign(Gtk.Align.END)
            lbl.set_margin_end(8)
            lbl.set_valign(Gtk.Align.START)
            lbl.set_margin_top(4)
            grid.attach(lbl, 0, row, 1, 1)
            grid.attach(sys_prompt_frame, 1, row, 1, 1)
            row += 1

            self._ai_entries[provider] = (key_entry, model_entry, sys_prompt_buf)

            if provider in ("ollama", "custom"):
                url_entry = Gtk.Entry()
                url_entry.set_text(urls.get(provider, ""))
                url_entry.set_placeholder_text(
                    "http://localhost:11434/v1/chat/completions" if provider == "ollama"
                    else "http://localhost:8080/v1/chat/completions"
                )
                url_entry.set_tooltip_text(
                    f"Base URL for the {title} API endpoint.\n"
                    + ("Must be an OpenAI-compatible chat completions endpoint.\n"
                       "Example: http://localhost:11434/v1/chat/completions" if provider == "ollama"
                       else "Must be an OpenAI-compatible chat completions endpoint.\n"
                       "Examples: http://localhost:8080/v1/chat/completions (llama.cpp), "
                       "http://localhost:8000/v1/chat/completions (vLLM)")
                )
                row = self._row(grid, row, "URL:", url_entry)
                self._ai_entries[provider + "_url"] = url_entry

            row += 1

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(grid)
        return sw

    def _build_notes(self):
        grid = Gtk.Grid()
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        grid.set_margin_top(8)
        grid.set_margin_bottom(8)
        grid.set_row_spacing(9)
        grid.set_column_spacing(12)
        row = 0

        row = self._section(grid, row, "Notes")
        self._entry_notes_dir = Gtk.Entry()
        self._entry_notes_dir.set_text(self._settings.get("notes_dir", ""))
        self._entry_notes_dir.set_placeholder_text(os.path.expanduser("~"))
        self._entry_notes_dir.set_tooltip_text("Directory where note files are stored. Default: home directory")
        row = self._row(grid, row, "Notes directory:", self._entry_notes_dir)

        self._entry_notes_file = Gtk.Entry()
        self._entry_notes_file.set_text(self._settings.get("notes_file", ""))
        self._entry_notes_file.set_placeholder_text("notes.md")
        self._entry_notes_file.set_tooltip_text("Default notes filename. Created automatically when you use /wnotes")
        row = self._row(grid, row, "Default notes file:", self._entry_notes_file)

        self._entry_editor = Gtk.Entry()
        self._entry_editor.set_text(self._settings.get("editor_command", "nano"))
        self._entry_editor.set_tooltip_text(
            "Fallback editor for /onotes, used only if xdg-open is unavailable. "
            "Normally /onotes opens your system's default app for .md files instead.")
        row = self._row(grid, row, "Fallback editor:", self._entry_editor)

        return grid

    def _on_response(self, dialog, response):
        if response != Gtk.ResponseType.OK:
            self.destroy()
            return

        s = self._settings
        s.begin_batch()

        s.set("tab_title", self._entry_title.get_text())
        dyn_map = {0: "replace", 1: "before", 2: "after", 3: "hide"}
        s.set("dynamic_title", dyn_map.get(self._combo_dynamic.get_active(), "replace"))

        s.set("login_shell", self._chk_login.get_active())
        s.set("shell_command", self._entry_shell.get_text())
        s.set("terminal_columns", int(self._spin_columns.get_value()))
        s.set("terminal_rows", int(self._spin_rows.get_value()))

        pos_map = {0: "right", 1: "left", 2: "disabled"}
        s.set("scrollbar_position", pos_map.get(self._combo_scrollbar_pos.get_active(), "right"))
        s.set("scrollback_lines", -1 if self._chk_scrollback_unlimited.get_active() else int(self._spin_scrollback.get_value()))
        s.set("scroll_on_output", self._chk_scroll_output.get_active())
        s.set("scroll_on_keystroke", self._chk_scroll_keystroke.get_active())

        s.set("confirm_close", self._chk_confirm_close.get_active())
        s.set("auto_copy_selection", self._chk_auto_copy.get_active())
        s.set("show_unsafe_paste_dialog", self._chk_warn_paste.get_active())
        s.set("file_manager", self._entry_fm.get_text())

        font_name = self._font_btn.get_font_name()
        parts = font_name.rsplit(" ", 1)
        if parts:
            s.set("font_name", parts[0])
        if len(parts) == 2 and parts[1].isdigit():
            s.set("font_size", int(parts[1]))
        s.set("allow_bold_text", self._chk_bold.get_active())

        scheme = self._combo_scheme.get_active_text()
        if scheme:
            s.set("color_scheme", scheme)

        s.set("foreground_color", self._fg_color_btn._hex)
        s.set("background_color", self._bg_color_btn._hex)
        s.set("cursor_color", self._cursor_color_btn._hex)
        s.set("highlight_color", self._highlight_btn._hex)
        s.set("highlight_bg_color", self._highlight_bg_btn._hex)

        s.set("tab_title_color", self._tab_title_color_btn._hex)
        s.set("tab_active_title_color", self._tab_active_color_btn._hex)

        s.set("cursor_shape", self._combo_cursor_shape.get_active_text())
        s.set("cursor_blink", self._chk_cursor_blink.get_active())
        s.set("opacity", self._spin_opacity.get_value())
        s.set("enable_transparency", self._chk_transparency.get_active())
        s.set("window_padding_horizontal", int(self._spin_pad_h.get_value()))
        s.set("window_padding_vertical", int(self._spin_pad_v.get_value()))
        s.set("undercurl_style", self._combo_undercurl.get_active_text() or "single")
        s.set("session_restore", self._chk_session_restore.get_active())
        s.set("bell_notification", self._chk_bell_notify.get_active())
        s.set("hint_mode_enabled", self._chk_hint_mode.get_active())
        s.set("vi_copy_mode_enabled", self._chk_vi_copy.get_active())

        palette = {key: btn._hex for key, btn in self._palette_btns.items()}
        scheme_name = self._combo_scheme.get_active_text() or "Dark (Default)"
        preset = COLOR_PALETTES.get(scheme_name, COLOR_PALETTES["Dark (Default)"])
        if palette != preset:
            s.set("custom_palette", palette)
        else:
            s.set("custom_palette", None)

        bs_map = {0: "auto", 1: "ascii-del", 2: "escape-sequence", 3: "control-h"}
        s.set("backspace_binding", bs_map.get(self._combo_backspace.get_active(), "ascii-del"))
        del_map = {0: "auto", 1: "escape-sequence", 2: "ascii-del", 3: "control-h"}
        s.set("delete_binding", del_map.get(self._combo_delete.get_active(), "escape-sequence"))
        s.set("encoding", self._combo_encoding.get_active_text() or "UTF-8")

        osc133_was_enabled = s.get("osc133", False)
        osc133_now_enabled = self._chk_osc133.get_active()
        s.set("osc133", osc133_now_enabled)

        new_keys = {}
        new_models = {}
        new_urls = {}
        new_sys_prompts = {}
        for key, val in self._ai_entries.items():
            if key.endswith("_url"):
                provider_name = key.replace("_url", "")
                if isinstance(val, Gtk.Entry):
                    new_urls[provider_name] = val.get_text()
            else:
                key_entry, model_entry, sys_prompt_buf = val
                new_keys[key] = key_entry.get_text()
                new_models[key] = model_entry.get_text()
                prompt = sys_prompt_buf.get_text(
                    sys_prompt_buf.get_start_iter(),
                    sys_prompt_buf.get_end_iter(), True
                ).strip()
                if prompt:
                    new_sys_prompts[key] = prompt
        s.set("ai_keys", new_keys)
        s.set("ai_models", new_models)
        s.set("ai_urls", new_urls)
        s.set("ai_system_prompts", new_sys_prompts)

        s.set("notes_dir", self._entry_notes_dir.get_text())
        s.set("notes_file", self._entry_notes_file.get_text())
        s.set("editor_command", self._entry_editor.get_text())

        s.end_batch()
        s.notify_changed()

        if osc133_now_enabled and not osc133_was_enabled:
            _write_osc_setup_script()
            script_path = os.path.join(
                os.path.expanduser("~"), ".config", "tpgk", "osc-setup.sh")
            osc_dialog = Gtk.MessageDialog(
                self, Gtk.DialogFlags.MODAL, Gtk.MessageType.INFO,
                Gtk.ButtonsType.OK,
                "OSC 133 shell integration setup script created:\n\n"
                f"{script_path}\n\n"
                "Run this script to add the integration to your\n"
                "~/.bashrc and ~/.zshrc:\n\n"
                f"  bash {script_path}\n\n"
                "After running, restart your shell or run:\n"
                "  source ~/.bashrc"
            )
            osc_dialog.run()
            osc_dialog.destroy()

        self.destroy()


def _write_osc_setup_script():
    script_dir = os.path.join(os.path.expanduser("~"), ".config", "tpgk")
    script_path = os.path.join(script_dir, "osc-setup.sh")
    script = r'''#!/bin/bash
# TPGK OSC 133 Shell Integration Setup
# Run this script to add OSC 133 integration to your shell config.
#   bash ~/.config/tpgk/osc-setup.sh

OSC133_LINE='[ -f ~/.config/tpgk/osc133.sh ] && source ~/.config/tpgk/osc133.sh'

for rc in ~/.bashrc ~/.zshrc; do
    if [ -f "$rc" ]; then
        if ! grep -qF "osc133.sh" "$rc" 2>/dev/null; then
            printf '\n# TPGK OSC 133 Shell Integration\n%s\n' "$OSC133_LINE" >> "$rc"
            echo "Added OSC 133 integration to $rc"
        else
            echo "OSC 133 already configured in $rc"
        fi
    fi
done

echo "Done. Restart your shell or run: source ~/.bashrc"
'''
    os.makedirs(script_dir, exist_ok=True)
    try:
        with open(script_path, "w") as f:
            f.write(script)
        os.chmod(script_path, 0o755)
    except OSError:
        pass


def _hex_to_rgba(hex_color: str) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    rgba.parse(hex_color)
    return rgba


def _rgba_to_hex(rgba: Gdk.RGBA) -> str:
    return f"#{int(rgba.red * 255):02x}{int(rgba.green * 255):02x}{int(rgba.blue * 255):02x}"
