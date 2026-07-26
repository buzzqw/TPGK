import os
import json

PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk", "profiles")


def profile_path(name):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    return os.path.join(PROFILE_DIR, f"{name}.json")


def list_profiles():
    if not os.path.isdir(PROFILE_DIR):
        return []
    files = sorted(
        [f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")])
    return files


def save_profile(name, settings_data):
    to_save = {}
    for key in ("font_name", "font_size", "color_scheme", "foreground_color",
                "background_color", "cursor_color", "cursor_shape",
                "highlight_color", "highlight_bg_color", "opacity",
                "enable_transparency", "scrollback_lines", "scrollbar_position",
                "custom_palette", "allow_bold_text", "cursor_blink",
                "tab_title_color", "tab_active_title_color",
                "shell_command", "login_shell", "encoding", "osc133",
                "backspace_binding", "delete_binding", "scroll_on_output",
                "scroll_on_keystroke", "window_padding_horizontal",
                "window_padding_vertical", "bell_notification",
                "undercurl_style"):
        if key in settings_data:
            to_save[key] = settings_data[key]
    try:
        with open(profile_path(name), "w") as f:
            json.dump(to_save, f, indent=2)
    except OSError:
        pass


def load_profile(name):
    p = profile_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def delete_profile(name):
    p = profile_path(name)
    if os.path.exists(p):
        os.unlink(p)


def apply_profile(settings_obj, name):
    data = load_profile(name)
    if not data:
        return False
    for k, v in data.items():
        settings_obj._data[k] = v
    settings_obj.save()
    settings_obj.notify_changed()
    return True
