import os
import datetime
import shlex
import shutil
import subprocess

from tpgk.settings import Settings


class NotesManager:
    def __init__(self):
        self._settings = Settings()

    def _get_notes_path(self, filename=None):
        if filename:
            if os.path.isabs(filename):
                return filename
            notes_dir = self._settings.get("notes_dir", os.path.expanduser("~"))
            return os.path.join(notes_dir, filename)
        configured = self._settings.get("notes_file", "")
        if configured and os.path.isfile(configured):
            return configured
        notes_dir = self._settings.get("notes_dir", os.path.expanduser("~"))
        name = configured if configured else "notes.md"
        if not name.endswith(".md"):
            name += ".md"
        return os.path.join(notes_dir, name)

    def write_note(self, text: str, filename=None):
        path = self._get_notes_path(filename)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## {ts}\n\n{text}\n"
        with open(path, "a") as f:
            f.write(entry)
        return path

    def open_notes(self, filename=None):
        path = self._get_notes_path(filename)
        if not os.path.isfile(path):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write("# TPGK Notes\n\n")

        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, path], start_new_session=True)
            return path

        editor = self._settings.get("editor_command", "nano")
        editor_parts = shlex.split(editor) if editor else ["nano"]
        subprocess.Popen(editor_parts + [path], start_new_session=True)
        return path
