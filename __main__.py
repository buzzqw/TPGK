#!/usr/bin/env python3
import sys
import os

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gtk, Gdk, Gio

from tpgk.settings import Settings
from tpgk.window import MainWindow


class TpgkApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.buzzqw.tpgk",
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self._settings = Settings()
        self._settings.load()

    def do_activate(self):
        win = MainWindow(self)
        self.add_window(win)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            vte-terminal { padding-left: 8px; padding-right: 4px; }
            .tpgk-menu-row { background: alpha(@theme_fg_color, 0.05); padding: 1px 4px; }
            .tpgk-menu-row button { padding: 3px 10px; }
            .command-bar-frame { border: 1px solid alpha(currentColor, 0.3); background: alpha(@theme_bg_color, 0.95); }
            .command-bar-frame entry { padding: 6px 10px; font-family: Monospace; }
            .command-bar-frame list row { padding: 2px 10px; }
            .command-bar-frame list row:selected { background: @theme_selected_bg_color; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main():
    app = TpgkApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
