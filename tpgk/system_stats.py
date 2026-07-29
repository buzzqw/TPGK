import psutil


def _mb(val: int) -> str:
    gb = 1024 * 1024 * 1024
    mb = 1024 * 1024
    if val >= gb:
        return f"{val / gb:.1f}G"
    return f"{val / mb:.0f}M"


def collect(is_ssh: bool = False) -> str:
    """Return a lightweight one-line stats string (CPU / RAM / Disk)."""
    prefix = "  [SSH] " if is_ssh else "  "
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return (
        f"{prefix}CPU {cpu:5.1f}%  "
        f"RAM {_mb(mem.used)}/{_mb(mem.total)} ({mem.percent:.0f}%)  "
        f"Disk {_mb(disk.used)}/{_mb(disk.total)} ({disk.percent:.0f}%)"
    )
