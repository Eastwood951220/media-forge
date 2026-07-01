"""Plain-text log file management utilities."""

import os
from pathlib import Path


def ensure_log_dir(log_dir: str) -> None:
    """Create log directory if it doesn't exist."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)


def append_log(log_dir: str, filename: str, line: str) -> None:
    """Append a line to a log file."""
    path = Path(log_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_logs(log_dir: str, filename: str) -> list[str]:
    """Load all lines from a log file."""
    path = Path(log_dir) / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def delete_log(log_dir: str, filename: str) -> None:
    """Delete a log file."""
    path = Path(log_dir) / filename
    if path.exists():
        os.remove(path)


def rotate_log(log_dir: str, filename: str, max_bytes: int = 10 * 1024 * 1024) -> None:
    """Rotate log file if it exceeds max_bytes. Keeps current + one backup."""
    path = Path(log_dir) / filename
    if not path.exists() or path.stat().st_size < max_bytes:
        return
    backup = path.with_suffix(path.suffix + ".1")
    if backup.exists():
        os.remove(backup)
    path.rename(backup)
