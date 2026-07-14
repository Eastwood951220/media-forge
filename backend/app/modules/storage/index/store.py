from __future__ import annotations

import json
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from shared.runtime_config import RuntimeConfigPaths
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord


class StorageIndexMissingError(RuntimeError):
    pass


class StorageIndexStore:
    TREE_VERSION = 1

    def __init__(self, paths: RuntimeConfigPaths | None = None) -> None:
        self.paths = paths or RuntimeConfigPaths.from_env()

    def read_metadata(self) -> StorageIndexMetadata:
        path = self.paths.storage_index_meta_file
        if not path.exists():
            return StorageIndexMetadata.never_built()
        return StorageIndexMetadata.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def write_running_metadata(self, metadata: StorageIndexMetadata) -> None:
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())

    @property
    def temp_index_file(self):
        return self.paths.storage_index_file.with_suffix(self.paths.storage_index_file.suffix + ".tmp")

    def begin_temp_index(self, target_folder: str | None = None):
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        if target_folder is None:
            temp_path.write_text("", encoding="utf-8")
        else:
            self.write_temp_tree(self.empty_tree(target_folder, indexed_at=None))
        return temp_path

    def append_temp_record(self, record: StorageIndexRecord) -> None:
        tree = self._read_tree_file(self.temp_index_file) if self.temp_index_file.exists() and self.temp_index_file.read_text(encoding="utf-8").strip() else self.empty_tree("", record.indexed_at)
        self._insert_record(tree, record)
        self.write_temp_tree(tree)

    def write_temp_tree(self, tree: dict[str, Any]) -> None:
        self._write_json_atomic(self.temp_index_file, tree)

    def finalize_temp_index(self, metadata: StorageIndexMetadata) -> StorageIndexMetadata:
        temp_path = self.temp_index_file
        if not temp_path.exists() or not temp_path.read_text(encoding="utf-8").strip():
            self.write_temp_tree(self.empty_tree(metadata.target_folder, metadata.completed_at or metadata.started_at))
        temp_path.replace(self.paths.storage_index_file)
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())
        return metadata

    def read_index_tree(self) -> dict[str, Any]:
        metadata = self.read_metadata()
        if metadata.status != "completed" or not self.paths.storage_index_file.exists():
            raise StorageIndexMissingError("存储索引不存在或尚未完成，请先刷新存储索引")
        try:
            return self._read_tree_file(self.paths.storage_index_file)
        except json.JSONDecodeError:
            raise StorageIndexMissingError("存储索引文件格式已过期或损坏，请重新刷新存储索引")

    def load_index_by_code(self) -> dict[str, list[StorageIndexRecord]]:
        tree = self.read_index_tree()
        grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
        for category_name, category in (tree.get("categories") or {}).items():
            for _folder_name, code_folder in (category.get("code_folders") or {}).items():
                code = str(code_folder.get("code") or "").upper()
                target_folder = str(code_folder.get("path") or "")
                for video in code_folder.get("videos") or []:
                    record = StorageIndexRecord(
                        code=code,
                        path=str(video["path"]),
                        target_folder=target_folder,
                        storage_location=str(category_name),
                        file_name=str(video["file_name"]),
                        size=int(video.get("size") or 0),
                        indexed_at=str(video["indexed_at"]),
                    )
                    grouped[record.code].append(record)
        return dict(grouped)

    def upsert_records(self, records: list[StorageIndexRecord], target_folder: str) -> None:
        try:
            tree = self.read_index_tree()
        except StorageIndexMissingError:
            tree = self.empty_tree(target_folder, indexed_at=None)
        for record in records:
            self._insert_record(tree, record)
        self._write_json_atomic(self.paths.storage_index_file, tree)

    def tree_from_records(self, target_folder: str, records: list[StorageIndexRecord], *, indexed_at: str | None) -> dict[str, Any]:
        tree = self.empty_tree(target_folder, indexed_at=indexed_at)
        for record in records:
            self._insert_record(tree, record)
        return tree

    def empty_tree(self, target_folder: str, indexed_at: str | None) -> dict[str, Any]:
        return {
            "version": self.TREE_VERSION,
            "target_folder": target_folder,
            "indexed_at": indexed_at,
            "categories": {},
        }

    def known_code_folder_paths(self) -> set[str]:
        try:
            tree = self.read_index_tree()
        except StorageIndexMissingError:
            return set()
        paths: set[str] = set()
        for category in (tree.get("categories") or {}).values():
            for code_folder in (category.get("code_folders") or {}).values():
                path = str(code_folder.get("path") or "")
                if path:
                    paths.add(path)
        return paths

    def _insert_record(self, tree: dict[str, Any], record: StorageIndexRecord) -> None:
        category = tree.setdefault("categories", {}).setdefault(record.storage_location, {
            "path": str(PurePosixPath(record.target_folder).parent),
            "code_folders": {},
        })
        folder_name = PurePosixPath(record.target_folder).name
        code_folder = category.setdefault("code_folders", {}).setdefault(folder_name, {
            "path": record.target_folder,
            "code": record.code,
            "videos": [],
        })
        videos = code_folder.setdefault("videos", [])
        videos[:] = [video for video in videos if video.get("path") != record.path]
        videos.append({
            "path": record.path,
            "file_name": record.file_name,
            "size": record.size,
            "indexed_at": record.indexed_at,
        })

    def _read_tree_file(self, path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json_atomic(self, path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
