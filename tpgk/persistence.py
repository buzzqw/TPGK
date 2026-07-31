import os


def validate_name(name: str, kind: str) -> str:
    if not isinstance(name, str):
        raise ValueError(f"{kind} name must be text")
    name = name.strip()
    if not name or name in {".", ".."}:
        raise ValueError(f"{kind} name cannot be empty")
    if len(name) > 100:
        raise ValueError(f"{kind} name is too long")
    if any(char in name for char in ("/", "\\", "\x00")) or any(ord(char) < 32 for char in name):
        raise ValueError(f"{kind} name contains invalid characters")
    if os.path.basename(name) != name:
        raise ValueError(f"{kind} name must not contain a path")
    return name
