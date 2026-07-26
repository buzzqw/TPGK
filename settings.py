import os
import json

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "font_name": "Monospace",
    "font_size": 12,
    "color_scheme": "Dark (Default)",
    "foreground_color": "",
    "background_color": "",
    "cursor_color": "#ffffff",
    "cursor_shape": "block",
    "highlight_color": "#ffffff",
    "highlight_bg_color": "#446688",
    "scrollback_lines": 10000,
    "scrollbar_position": "right",
    "opacity": 1.0,
    "shell_command": os.environ.get("SHELL", "/bin/bash"),
    "notes_file": "",
    "notes_dir": os.path.expanduser("~"),
    "editor_command": os.environ.get("EDITOR", "nano"),
    "ai_provider": "",
    "ai_models": {
        "openai": "", "claude": "", "gemini": "",
        "deepseek": "", "ollama": "", "custom": "",
    },
    "ai_urls": {
        "ollama": "http://localhost:11434/v1/chat/completions",
        "custom": "",
    },
    "ai_keys": {
        "openai": "", "claude": "", "gemini": "",
        "deepseek": "", "ollama": "", "custom": "",
    },
    "ai_last_provider": "",
    "ai_system_prompts": {},
    "osc133": False,
    "enable_transparency": False,
    "confirm_close": True,
    "tab_title": "Terminal",
    "tab_title_color": "#ffffff",
    "tab_active_title_color": "#ffffff",
    "encoding": "UTF-8",
    "auto_copy_selection": True,
    "file_manager": "",
    "backspace_binding": "ascii-del",
    "delete_binding": "escape-sequence",
    "custom_palette": None,
    "show_unsafe_paste_dialog": True,
    "show_tabs": True,
    "show_menubar": True,
    "show_toolbar": True,
    "show_stats": False,
    "dynamic_title": "replace",
    "login_shell": True,
    "cursor_blink": True,
    "scroll_on_output": True,
    "scroll_on_keystroke": True,
    "allow_bold_text": True,
    "terminal_columns": 80,
    "terminal_rows": 24,
    "window_padding_horizontal": 2,
    "window_padding_vertical": 2,
    "bell_notification": False,
    "undercurl_style": "single",
    "broadcast_input": False,
    "active_profile": "",
    "session_restore": True,
}

COLOR_SCHEMES = {
    "Dark (Default)": {
        "foreground": "#d3d7cf", "background": "#0a0a0a",
    },
    "Light": {
        "foreground": "#2e3436", "background": "#ffffff",
    },
    "Solarized Dark": {
        "foreground": "#839496", "background": "#002b36",
    },
    "Solarized Light": {
        "foreground": "#657b83", "background": "#fdf6e3",
    },
    "Gruvbox Dark": {
        "foreground": "#ebdbb2", "background": "#282828",
    },
    "Monokai": {
        "foreground": "#f8f8f2", "background": "#272822",
    },
    "Nord": {
        "foreground": "#e5e9f0", "background": "#3b4252",
    },
    "Matrix": {
        "foreground": "#00ff41", "background": "#0d0208",
    },
}

COLOR_PALETTES = {
    "Dark (Default)": {
        "black": "#0a0a0a", "red": "#cc0000", "green": "#4e9a06",
        "yellow": "#c4a000", "blue": "#3465a4", "magenta": "#75507b",
        "cyan": "#06989a", "white": "#d3d7cf",
        "brightblack": "#555753", "brightred": "#ef2929",
        "brightgreen": "#8ae234", "brightyellow": "#fce94f",
        "brightblue": "#729fcf", "brightmagenta": "#ad7fa8",
        "brightcyan": "#34e2e2", "brightwhite": "#eeeeec",
    },
    "Light": {
        "black": "#2e3436", "red": "#cc0000", "green": "#4e9a06",
        "yellow": "#c4a000", "blue": "#3465a4", "magenta": "#75507b",
        "cyan": "#06989a", "white": "#d3d7cf",
        "brightblack": "#555753", "brightred": "#ef2929",
        "brightgreen": "#8ae234", "brightyellow": "#fce94f",
        "brightblue": "#729fcf", "brightmagenta": "#ad7fa8",
        "brightcyan": "#34e2e2", "brightwhite": "#eeeeec",
    },
    "Solarized Dark": {
        "black": "#002b36", "red": "#dc322f", "green": "#859900",
        "yellow": "#b58900", "blue": "#268bd2", "magenta": "#d33682",
        "cyan": "#2aa198", "white": "#eee8d5",
        "brightblack": "#073642", "brightred": "#cb4b16",
        "brightgreen": "#586e75", "brightyellow": "#657b83",
        "brightblue": "#839496", "brightmagenta": "#6c71c4",
        "brightcyan": "#93a1a1", "brightwhite": "#fdf6e3",
    },
    "Solarized Light": {
        "black": "#073642", "red": "#dc322f", "green": "#859900",
        "yellow": "#b58900", "blue": "#268bd2", "magenta": "#d33682",
        "cyan": "#2aa198", "white": "#eee8d5",
        "brightblack": "#002b36", "brightred": "#cb4b16",
        "brightgreen": "#586e75", "brightyellow": "#657b83",
        "brightblue": "#839496", "brightmagenta": "#6c71c4",
        "brightcyan": "#93a1a1", "brightwhite": "#fdf6e3",
    },
    "Gruvbox Dark": {
        "black": "#282828", "red": "#cc241d", "green": "#98971a",
        "yellow": "#d79921", "blue": "#458588", "magenta": "#b16286",
        "cyan": "#689d6a", "white": "#a89984",
        "brightblack": "#928374", "brightred": "#fb4934",
        "brightgreen": "#b8bb26", "brightyellow": "#fabd2f",
        "brightblue": "#83a598", "brightmagenta": "#d3869b",
        "brightcyan": "#8ec07c", "brightwhite": "#ebdbb2",
    },
    "Monokai": {
        "black": "#272822", "red": "#f92672", "green": "#a6e22e",
        "yellow": "#f4bf75", "blue": "#66d9ef", "magenta": "#ae81ff",
        "cyan": "#a1efe4", "white": "#f8f8f2",
        "brightblack": "#75715e", "brightred": "#f92672",
        "brightgreen": "#a6e22e", "brightyellow": "#f4bf75",
        "brightblue": "#66d9ef", "brightmagenta": "#ae81ff",
        "brightcyan": "#a1efe4", "brightwhite": "#f9f8f5",
    },
    "Nord": {
        "black": "#3b4252", "red": "#bf616a", "green": "#a3be8c",
        "yellow": "#ebcb8b", "blue": "#81a1c1", "magenta": "#b48ead",
        "cyan": "#88c0d0", "white": "#e5e9f0",
        "brightblack": "#4c566a", "brightred": "#bf616a",
        "brightgreen": "#a3be8c", "brightyellow": "#ebcb8b",
        "brightblue": "#81a1c1", "brightmagenta": "#b48ead",
        "brightcyan": "#8fbcbb", "brightwhite": "#eceff4",
    },
    "Matrix": {
        "black": "#0d0208", "red": "#008f11", "green": "#00ff41",
        "yellow": "#00ff41", "blue": "#008f11", "magenta": "#00ff41",
        "cyan": "#00ff41", "white": "#00ff41",
        "brightblack": "#003b00", "brightred": "#00ff41",
        "brightgreen": "#00ff41", "brightyellow": "#00ff41",
        "brightblue": "#00ff41", "brightmagenta": "#00ff41",
        "brightcyan": "#00ff41", "brightwhite": "#00ff41",
    },
}


class Settings:
    _instance = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = dict(DEFAULTS)
            cls._instance._callbacks = []
        return cls._instance

    def connect(self, callback):
        self._callbacks.append(callback)

    def disconnect(self, callback):
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def notify_changed(self):
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def _ensure_loaded(self):
        if self._loaded:
            return
        self.load()

    def load(self):
        if self._loaded:
            return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.chmod(CONFIG_DIR, 0o700)
        if os.path.exists(CONFIG_FILE):
            try:
                os.chmod(CONFIG_FILE, 0o600)
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                for key in DEFAULTS:
                    if key in data:
                        self._data[key] = data[key]
            except (json.JSONDecodeError, OSError):
                self.save()
        else:
            self.save()
        self._loaded = True

    def save(self):
        import tempfile
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.chmod(CONFIG_DIR, 0o700)
        # Fix #15: atomic write — a crash mid-write cannot corrupt the existing config
        fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".settings_tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._data, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, CONFIG_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get(self, key, default=None):
        self._ensure_loaded()
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self.save()

    def get_color_scheme(self):
        self._ensure_loaded()
        scheme = self._data.get("color_scheme", "Dark (Default)")
        return COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["Dark (Default)"])

    def get_palette(self):
        self._ensure_loaded()
        custom = self._data.get("custom_palette")
        if custom:
            return custom
        scheme = self._data.get("color_scheme", "Dark (Default)")
        return COLOR_PALETTES.get(scheme, COLOR_PALETTES["Dark (Default)"])

    def get_fg_color(self):
        self._ensure_loaded()
        explicit = self._data.get("foreground_color", "")
        if explicit:
            return explicit
        return self.get_color_scheme()["foreground"]

    def get_bg_color(self):
        self._ensure_loaded()
        explicit = self._data.get("background_color", "")
        if explicit:
            return explicit
        return self.get_color_scheme()["background"]
