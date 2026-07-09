from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from backend.app.modules.content.movies.storage_scan import is_matching_video, remote_entry_to_dict
from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.database.models.content import Movie


class StorageIndexRefreshService:
    def __init__(self, store: StorageIndexStore | None = None) -> None:
        self.store = store or StorageIndexStore()

    def refresh(self, config: dict, provider, *, force_refresh_mode: str = "none") -> StorageIndexMetadata:
        target_root = str(config.get("target_folder") or "/Movies").rstrip("/")
        started_at = datetime.now(timezone.utc).isoformat()
        self.store.write_running_metadata(StorageIndexMetadata(target_folder=target_root, status="running", started_at=started_at))
        errors: list[dict] = []
        category_count = 0
        code_folder_count = 0
        video_count = 0
        self.store.begin_temp_index()

        try:
            categories = self._safe_list(provider, target_root, force_refresh=False, errors=errors)
            for category_entry in categories:
                category = remote_entry_to_dict(category_entry, target_root)
                if not category["is_dir"] or not category["name"]:
                    continue
                category_count += 1
                category_folder = category["path"] or str(PurePosixPath(target_root) / category["name"])
                code_folders = self._safe_list(provider, category_folder, force_refresh=False, errors=errors)
                for code_entry in code_folders:
                    code_folder_item = remote_entry_to_dict(code_entry, category_folder)
                    if not code_folder_item["is_dir"] or not code_folder_item["name"]:
                        continue
                    code_folder_count += 1
                    code_folder = code_folder_item["path"] or str(PurePosixPath(category_folder) / code_folder_item["name"])
                    self.store.write_running_metadata(StorageIndexMetadata(
                        target_folder=target_root,
                        status="running",
                        started_at=started_at,
                        category_count=category_count,
                        code_folder_count=code_folder_count,
                        video_count=video_count,
                        force_refresh_mode=force_refresh_mode,
                        current_path=code_folder,
                        errors=errors,
                    ))
                    files = self._safe_list(provider, code_folder, force_refresh=False, errors=errors)
                    for record in self._records_from_files(files, code_folder, category["name"], config, started_at):
                        self.store.append_temp_record(record)
                        video_count += 1
        except Exception as exc:
            failed = StorageIndexMetadata(target_folder=target_root, status="failed", started_at=started_at, errors=[{"path": target_root, "error": str(exc)}])
            self.store.write_running_metadata(failed)
            raise

        completed = StorageIndexMetadata(
            target_folder=target_root,
            status="completed",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            category_count=category_count,
            code_folder_count=code_folder_count,
            video_count=video_count,
            force_refresh_mode=force_refresh_mode,
            errors=errors,
        )
        return self.store.finalize_temp_index(completed)

    def _safe_list(self, provider, path: str, *, force_refresh: bool, errors: list[dict]):
        try:
            return provider.list_files(path, force_refresh=force_refresh)
        except TypeError:
            try:
                return provider.list_files(path)
            except Exception as exc:
                errors.append({"path": path, "error": str(exc)})
                return []
        except Exception as exc:
            errors.append({"path": path, "error": str(exc)})
            return []

    def _records_from_files(self, files, code_folder: str, storage_location: str, config: dict, indexed_at: str) -> list[StorageIndexRecord]:
        records: list[StorageIndexRecord] = []
        folder_name = PurePosixPath(code_folder).name
        base_code = _base_code_from_folder(folder_name)
        movie_stub = Movie(code=base_code)
        for file_entry in files:
            item = remote_entry_to_dict(file_entry, code_folder)
            if not is_matching_video(movie_stub, item, config):
                continue
            records.append(StorageIndexRecord(
                code=base_code,
                path=item["path"],
                target_folder=code_folder,
                storage_location=storage_location,
                file_name=item["name"],
                size=item["size"],
                indexed_at=indexed_at,
            ))
        return records


def _base_code_from_folder(folder_name: str) -> str:
    upper = folder_name.upper()
    for suffix in ("-UC", "-C", "-U"):
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper
