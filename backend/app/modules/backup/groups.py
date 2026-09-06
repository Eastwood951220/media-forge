from typing import Literal

BackupGroup = Literal["movies", "tasks", "config"]
DEFAULT_BACKUP_GROUPS: tuple[BackupGroup, ...] = ("movies", "tasks", "config")
BACKUP_FORMAT_NAME = "media-forge-backup"
BACKUP_FORMAT_VERSION = 1
