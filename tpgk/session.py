import os
import json
import time
import tempfile
from tpgk.logging_utils import get_logger
from tpgk.persistence import validate_name

SESSION_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk", "sessions")
logger = get_logger(__name__)
_SPLIT_MODES = {"single", "vertical", "horizontal"}
_MAX_TABS = 100


def _ensure_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)
    os.chmod(SESSION_DIR, 0o700)


def session_path(name="last"):
    _ensure_dir()
    name = validate_name(name, "Session")
    return os.path.join(SESSION_DIR, f"{name}.json")


def save_state(window, name="last"):
    data = {
        "timestamp": time.time(),
        "split_mode": window._split_mode,
        "tabs_left": [],
        "tabs_right": [],
    }
    for nb, key in ((window._notebook, "tabs_left"), (window._notebook2, "tabs_right")):
        for i in range(nb.get_n_pages()):
            page = nb.get_nth_page(i)
            title = window._tab_base_titles.get(page, window._get_tab_text(page))
            cwd = page.get_cwd() if page else os.path.expanduser("~")
            data[key].append({
                "base_title": title,
                "title": window._get_tab_text(page),
                "cwd": cwd,
            })
    _ensure_dir()
    path = session_path(name)
    try:
        fd, tmp = tempfile.mkstemp(dir=SESSION_DIR, prefix=".session_tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        logger.exception("session_save_failed")
        return False
    return True


def _validate_tab(tab):
    if not isinstance(tab, dict):
        return None
    cwd = tab.get("cwd", "")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")
    base_title = tab.get("base_title", tab.get("title", ""))
    title = tab.get("title", base_title)
    if not isinstance(base_title, str) or not isinstance(title, str):
        return None
    return {"cwd": cwd, "base_title": base_title[:200], "title": title[:200]}


def _validate_state(data):
    if not isinstance(data, dict) or data.get("split_mode", "single") not in _SPLIT_MODES:
        return None
    tabs = {}
    for key in ("tabs_left", "tabs_right"):
        values = data.get(key, [])
        if not isinstance(values, list) or len(values) > _MAX_TABS:
            return None
        tabs[key] = []
        for tab in values:
            validated = _validate_tab(tab)
            if validated is None:
                return None
            tabs[key].append(validated)
    if not tabs["tabs_left"]:
        return None
    return {"split_mode": data.get("split_mode", "single"), **tabs}


def load_state(name="last"):
    p = session_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            data = _validate_state(json.load(f))
            if data is None:
                logger.warning("session_load_invalid")
            return data
    except (json.JSONDecodeError, OSError):
        logger.exception("session_load_failed")
        return None


def list_sessions():
    if not os.path.isdir(SESSION_DIR):
        return []
    files = sorted(
        [f[:-5] for f in os.listdir(SESSION_DIR)
         if f.endswith(".json") and f != "last.json"
         and _valid_listed_name(f[:-5])],
        reverse=True)
    return files


def _valid_listed_name(name):
    try:
        validate_name(name, "Session")
    except ValueError:
        return False
    return True


def delete_session(name):
    p = session_path(name)
    if os.path.exists(p):
        os.unlink(p)


def restore_window(window, data):
    if not data:
        return
    split = data.get("split_mode", "single")
    tabs_left = data.get("tabs_left", [])
    tabs_right = data.get("tabs_right", [])

    if tabs_left:
        first = tabs_left[0]
        window._add_new_tab(cwd=first["cwd"], base_title=first["base_title"],
                            display_title=first["title"])
        for tab in tabs_left[1:]:
            window._add_new_tab(cwd=tab["cwd"], base_title=tab["base_title"],
                                display_title=tab["title"])

    if tabs_right and split != "single":
        window._set_split(split, create_tab=False)
        for tab in tabs_right:
            window._add_new_tab(cwd=tab["cwd"], target_notebook=window._notebook2,
                                base_title=tab["base_title"], display_title=tab["title"])
