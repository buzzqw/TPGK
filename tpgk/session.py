import os
import json
import time
import tempfile

SESSION_DIR = os.path.join(os.path.expanduser("~"), ".config", "tpgk", "sessions")


def _ensure_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)
    os.chmod(SESSION_DIR, 0o700)


def session_path(name="last"):
    _ensure_dir()
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
            data[key].append({"title": title, "cwd": cwd})
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
        pass


def load_state(name="last"):
    p = session_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_sessions():
    if not os.path.isdir(SESSION_DIR):
        return []
    files = sorted(
        [f[:-5] for f in os.listdir(SESSION_DIR)
         if f.endswith(".json") and f != "last.json"],
        reverse=True)
    return files


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
        window._add_new_tab(cwd=tabs_left[0].get("cwd"))
        for tab in tabs_left[1:]:
            window._add_new_tab(cwd=tab.get("cwd"))

    if tabs_right and split != "single":
        window._set_split(split)
        for tab in tabs_right:
            window._add_new_tab(cwd=tab.get("cwd"))
