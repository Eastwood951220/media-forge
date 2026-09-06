from __future__ import annotations

from pathlib import Path

BACKUP_FILE_SUFFIX = ".mfbackup"


def safe_backup_file_path(backup_dir: Path, name: str) -> Path:
    """Resolve a backup file name inside ``backup_dir`` or raise ``ValueError``.

    Only plain ``*.mfbackup`` file names are accepted so callers can never
    escape the configured backup directory through path traversal.
    """
    candidate = Path(name)
    if candidate.name != name or name == "" or candidate.suffix != BACKUP_FILE_SUFFIX:
        raise ValueError("Invalid backup file name")
    return backup_dir / name


def is_backup_file_name(name: str) -> bool:
    return Path(name).name == name and name.endswith(BACKUP_FILE_SUFFIX)
