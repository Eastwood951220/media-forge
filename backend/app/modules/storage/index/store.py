from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from shared.runtime_config import RuntimeConfigPaths
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord


class StorageIndexMissingError(RuntimeError):
    pass


class StorageIndexStore:
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
    def temp_index_file(self) -> Path:
        return self.paths.storage_index_file.with_suffix(self.paths.storage_index_file.suffix + ".tmp")

    def begin_temp_index(self) -> Path:
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text("", encoding="utf-8")
        return temp_path

    def append_temp_record(self, record: StorageIndexRecord) -> None:
        temp_path = self.temp_index_file
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            handle.flush()

    def finalize_temp_index(self, metadata: StorageIndexMetadata) -> StorageIndexMetadata:
        temp_path = self.temp_index_file
        if not temp_path.exists():
            temp_path.write_text("", encoding="utf-8")
        temp_path.replace(self.paths.storage_index_file)
        self._write_json_atomic(self.paths.storage_index_meta_file, metadata.to_dict())
        return metadata

    def load_index_by_code(self) -> dict[str, list[StorageIndexRecord]]:
        metadata = self.read_metadata()
        if metadata.status != "completed" or not self.paths.storage_index_file.exists():
            raise StorageIndexMissingError("存储索引不存在或尚未完成，请先刷新存储索引")
        grouped: dict[str, list[StorageIndexRecord]] = defaultdict(list)
        with self.paths.storage_index_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = StorageIndexRecord.from_dict(json.loads(line))
                grouped[record.code].append(record)
        return dict(grouped)

    def _write_json_atomic(self, path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
