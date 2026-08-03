import os

import psutil

_proc = psutil.Process(os.getpid())


def _mb(val: int) -> str:
    gb = 1024 * 1024 * 1024
    mb = 1024 * 1024
    if val >= gb:
        return f"{val / gb:.1f}G"
    return f"{val / mb:.0f}M"


def collect(is_ssh: bool = False) -> str:
    """Return a lightweight one-line stats string (CPU / RAM / Disk)."""
    if is_ssh:
        return ssh_placeholder()
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return (
        f"  CPU {cpu:5.1f}%  "
        f"RAM {_mb(mem.used)}/{_mb(mem.total)} ({mem.percent:.0f}%)  "
        f"Disk {_mb(disk.used)}/{_mb(disk.total)} ({disk.percent:.0f}%)"
    )


def collect_self() -> str:
    with _proc.oneshot():
        cpu = _proc.cpu_percent()
        mem = _proc.memory_info()
    return f"TPGK  CPU {cpu:5.1f}%  RAM {_mb(mem.rss)}  "


def ssh_placeholder() -> str:
    return "  [SSH] Remote session"
