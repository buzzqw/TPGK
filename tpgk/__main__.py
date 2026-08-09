#!/usr/bin/env python3
import sys
import os
import argparse

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gtk, Gdk, Gio, GLib

from tpgk.settings import Settings
from tpgk.window import MainWindow
from tpgk import __version__
from tpgk.logging_utils import configure_logging


GLib.set_prgname("tpgk")
GLib.set_application_name("TPGK Terminal")


def _parse_cli(argv):
    parser = argparse.ArgumentParser(prog="tpgk", description="TPGK terminal emulator")
    parser.add_argument("directory", nargs="?", help="Working directory for the new terminal")
    parser.add_argument("-w", "--working-directory", dest="working_directory",
                        help="Working directory for the new terminal")
    parser.add_argument("--new-window", action="store_true", help="Open a new window")
    parser.add_argument("--no-restore", action="store_true", help="Do not restore the last session")
    parser.add_argument("-e", "--execute", nargs=argparse.REMAINDER,
                        help="Run a command instead of the configured shell")
    parser.add_argument("--version", action="store_true", help="Show the TPGK version")
    options = parser.parse_args(argv)
    if options.directory and options.working_directory:
        parser.error("directory and --working-directory cannot be used together")
    options.requested_dir = options.working_directory or options.directory
    if options.requested_dir:
        options.start_dir = os.path.abspath(os.path.expanduser(options.requested_dir))
        if not os.path.isdir(options.start_dir):
            parser.error(f"not a directory: {options.start_dir}")
    else:
        options.start_dir = os.getcwd()
    if options.execute == []:
        parser.error("--execute requires a command")
    return options


class TpgkApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.buzzqw.tpgk",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self._settings = Settings()

    def do_activate(self):
        windows = self.get_windows()
        if windows:
            windows[0].present()
            return
        self._open_window()

    def _open_window(self, start_dir=None, command=None, restore_session=True):
        win = MainWindow(self, start_dir=start_dir, command=command, restore_session=restore_session)
        self.add_window(win)
        win.present()
        return win

    def do_command_line(self, command_line):
        try:
            options = _parse_cli(command_line.get_arguments()[1:])
        except SystemExit as error:
            return int(error.code) if isinstance(error.code, int) else 2
        if options.version:
            print(f"TPGK {__version__}")
            return 0

        windows = self.get_windows()
        explicit_open = bool(options.requested_dir or options.execute or options.new_window)
        if windows and not explicit_open:
            windows[0].present()
            return 0
        self._open_window(
            start_dir=options.start_dir,
            command=options.execute,
            restore_session=not (options.no_restore or explicit_open),
        )
        return 0

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
            popover { background-color: @theme_bg_color; }
            popover contents modelbutton { color: @theme_fg_color; padding: 8px 12px; min-height: 24px; }
            .tpgk-tab-menu { min-width: 220px; }
            .tpgk-tab-menu menuitem { padding: 6px 12px; min-height: 24px; }
            .tpgk-stats-label { font-size: 0.85em; font-family: Monospace; color: alpha(@theme_fg_color, 0.6); background: alpha(@theme_bg_color, 0.5); padding: 2px 12px; }
            .tpgk-hint-label { background: #fce94f; color: #000000; font-family: Monospace; font-weight: bold; font-size: 0.85em; padding: 1px 3px; border-radius: 2px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main():
    configure_logging()
    app = TpgkApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
