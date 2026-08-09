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
        notes_dir = os.path.abspath(os.path.expanduser(
            self._settings.get("notes_dir", os.path.expanduser("~"))))
        root = os.path.realpath(notes_dir)
        configured = self._settings.get("notes_file", "")
        name = filename or configured or "notes.md"
        if os.path.isabs(name):
            if filename is not None:
                raise ValueError("Note filename must be relative to the notes directory")
            return os.path.abspath(os.path.expanduser(name))
        if not name.endswith(".md"):
            name += ".md"
        path = os.path.abspath(os.path.join(notes_dir, name))
        parent = os.path.realpath(os.path.dirname(path))
        try:
            inside = os.path.commonpath((root, parent)) == root
        except ValueError:
            inside = False
        if not inside:
            raise ValueError("Note filename must stay inside the notes directory")
        return path

    @staticmethod
    def _open_flags(flags):
        return flags | getattr(os, "O_NOFOLLOW", 0)

    def _ensure_parent(self, path, allow_configured_external=False):
        notes_dir = os.path.realpath(os.path.abspath(os.path.expanduser(
            self._settings.get("notes_dir", os.path.expanduser("~")))))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        parent = os.path.realpath(os.path.dirname(path) or ".")
        if (not allow_configured_external
                and os.path.commonpath((notes_dir, parent)) != notes_dir):
            raise ValueError("Note path escapes the notes directory")

    def write_note(self, text: str, filename=None):
        path = self._get_notes_path(filename)
        configured = self._settings.get("notes_file", "")
        allow_external = filename is None and os.path.isabs(configured)
        self._ensure_parent(path, allow_configured_external=allow_external)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## {ts}\n\n{text}\n"
        fd = os.open(path, self._open_flags(os.O_CREAT | os.O_WRONLY | os.O_APPEND), 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(entry)
            os.fchmod(f.fileno(), 0o600)
        return path

    def open_notes(self, filename=None):
        path = self._get_notes_path(filename)
        configured = self._settings.get("notes_file", "")
        allow_external = filename is None and os.path.isabs(configured)
        self._ensure_parent(path, allow_configured_external=allow_external)
        if os.path.islink(path):
            raise ValueError("Note path must not be a symbolic link")
        if not os.path.isfile(path):
            fd = os.open(path, self._open_flags(os.O_CREAT | os.O_WRONLY | os.O_EXCL), 0o600)
            with os.fdopen(fd, "w") as f:
                f.write("# TPGK Notes\n\n")
                os.fchmod(f.fileno(), 0o600)

        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, path], start_new_session=True)
            return path

        editor = self._settings.get("editor_command", "nano")
        editor_parts = shlex.split(editor) if editor else ["nano"]
        subprocess.Popen(editor_parts + [path], start_new_session=True)
        return path
