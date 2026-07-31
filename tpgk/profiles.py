import os
import json
import tempfile
import re
from tpgk.logging_utils import get_logger
from tpgk.persistence import validate_name
from tpgk.settings import DEFAULTS

PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk", "profiles")
logger = get_logger(__name__)
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _ensure_dir():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)


def profile_path(name):
    _ensure_dir()
    name = validate_name(name, "Profile")
    return os.path.join(PROFILE_DIR, f"{name}.json")


def list_profiles():
    if not os.path.isdir(PROFILE_DIR):
        return []
    files = sorted(
        [f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")
         and _valid_listed_name(f[:-5])])
    return files


def _valid_listed_name(name):
    try:
        validate_name(name, "Profile")
    except ValueError:
        return False
    return True


def _validate_profile(data):
    if not isinstance(data, dict):
        return None
    valid = {}
    for key in _PROFILE_KEYS:
        if key not in data:
            continue
        value = data[key]
        default = DEFAULTS[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                return None
        elif isinstance(default, int):
            if not isinstance(value, int) or isinstance(value, bool):
                return None
            if key == "font_size" and not 4 <= value <= 128:
                return None
            if key == "scrollback_lines" and not 0 <= value <= 1_000_000:
                return None
            if key.startswith("window_padding_") and not 0 <= value <= 100:
                return None
        elif isinstance(default, float):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return None
            if key == "opacity" and not 0.1 <= value <= 1.0:
                return None
        elif isinstance(default, str):
            if not isinstance(value, str) or len(value) > 4096:
                return None
        elif isinstance(default, dict):
            if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                  or len(k) > 100 or len(v) > 4096
                                                  for k, v in value.items()):
                return None
        elif value is not None:
            return None
        valid[key] = value
    palette = valid.get("custom_palette")
    if palette is not None and (not isinstance(palette, dict) or
                                any(not _COLOR_RE.fullmatch(value) for value in palette.values())):
        return None
    return valid


_PROFILE_KEYS = (
    "font_name", "font_size", "color_scheme", "foreground_color", "background_color",
    "cursor_color", "cursor_shape", "highlight_color", "highlight_bg_color", "opacity",
    "enable_transparency", "scrollback_lines", "scrollbar_position", "custom_palette",
    "allow_bold_text", "cursor_blink", "tab_title_color", "tab_active_title_color",
    "shell_command", "login_shell", "encoding", "osc133", "backspace_binding",
    "delete_binding", "scroll_on_output", "scroll_on_keystroke", "window_padding_horizontal",
    "window_padding_vertical", "bell_notification", "undercurl_style",
)


def save_profile(name, settings_data):
    to_save = {}
    for key in _PROFILE_KEYS:
        if key in settings_data:
            to_save[key] = settings_data[key]
    to_save = _validate_profile(to_save)
    if to_save is None:
        raise ValueError("Profile contains invalid settings")
    _ensure_dir()
    path = profile_path(name)
    try:
        fd, tmp = tempfile.mkstemp(dir=PROFILE_DIR, prefix=".profile_tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(to_save, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        logger.exception("profile_save_failed")
        return False
    return True


def load_profile(name):
    p = profile_path(name)
    if not os.path.exists(p):
        return None
    try:
        os.chmod(p, 0o600)
        with open(p) as f:
            data = _validate_profile(json.load(f))
            if data is None:
                logger.warning("profile_load_invalid")
            return data
    except (json.JSONDecodeError, OSError):
        logger.exception("profile_load_failed")
        return None


def delete_profile(name):
    p = profile_path(name)
    if os.path.exists(p):
        os.unlink(p)


def apply_profile(settings_obj, name):
    data = load_profile(name)
    if not data:
        return False
    settings_obj.set_many(data)
    settings_obj.notify_changed()
    return True
