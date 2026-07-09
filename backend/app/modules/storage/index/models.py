from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


IndexStatus = Literal["never_built", "running", "completed", "failed"]


@dataclass(frozen=True)
class StorageIndexRecord:
    code: str
    path: str
    target_folder: str
    storage_location: str
    file_name: str
    size: int
    indexed_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StorageIndexRecord":
        return cls(
            code=str(data["code"]),
            path=str(data["path"]),
            target_folder=str(data["target_folder"]),
            storage_location=str(data.get("storage_location") or ""),
            file_name=str(data["file_name"]),
            size=int(data.get("size") or 0),
            indexed_at=str(data["indexed_at"]),
        )


@dataclass(frozen=True)
class StorageIndexMetadata:
    target_folder: str
    status: IndexStatus
    started_at: str | None = None
    completed_at: str | None = None
    category_count: int = 0
    code_folder_count: int = 0
    video_count: int = 0
    force_refresh_mode: str = "none"
    current_path: str | None = None
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def never_built(cls) -> "StorageIndexMetadata":
        return cls(target_folder="", status="never_built")

    @classmethod
    def from_dict(cls, data: dict) -> "StorageIndexMetadata":
        return cls(
            target_folder=str(data.get("target_folder") or ""),
            status=str(data.get("status") or "never_built"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            category_count=int(data.get("category_count") or 0),
            code_folder_count=int(data.get("code_folder_count") or 0),
            video_count=int(data.get("video_count") or 0),
            force_refresh_mode=str(data.get("force_refresh_mode") or "none"),
            current_path=data.get("current_path"),
            errors=list(data.get("errors") or []),
        )
