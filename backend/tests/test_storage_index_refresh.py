from dataclasses import dataclass

from backend.app.modules.storage.index.refresh import StorageIndexRefreshService
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


@dataclass
class RemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False


def test_refresh_builds_index_without_force_refreshing_code_folders(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )

    class Provider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append((path, force_refresh))
            if path == "/嘿嘿/日本":
                return [RemoteFile("巨乳|熟女|BBW", "/嘿嘿/日本/巨乳|熟女|BBW", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW":
                return [RemoteFile("ALDN-206-U", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U":
                return [RemoteFile("ALDN-206-U.mp4", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4", 500 * 1024 * 1024)]
            return []

    provider = Provider()
    service = StorageIndexRefreshService(StorageIndexStore(paths))

    metadata = service.refresh(
        {"target_folder": "/嘿嘿/日本", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider,
    )

    assert metadata.status == "completed"
    assert metadata.video_count == 1
    assert all(force_refresh is False for _path, force_refresh in provider.calls)
    assert not StorageIndexStore(paths).temp_index_file.exists()
    grouped = StorageIndexStore(paths).load_index_by_code()
    assert grouped["ALDN-206"][0].storage_location == "巨乳|熟女|BBW"


def test_refresh_writes_running_records_to_temp_jsonl(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)

    class Provider:
        def list_files(self, path, force_refresh=False):
            if path == "/嘿嘿/日本":
                assert store.temp_index_file.exists()
                return [RemoteFile("巨乳|熟女|BBW", "/嘿嘿/日本/巨乳|熟女|BBW", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW":
                return [RemoteFile("ALDN-206-U", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U", 0, True)]
            if path == "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U":
                return [RemoteFile("ALDN-206-U.mp4", "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4", 500 * 1024 * 1024)]
            return []

    StorageIndexRefreshService(store).refresh(
        {"target_folder": "/嘿嘿/日本", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        Provider(),
    )

    assert paths.storage_index_file.exists()
    assert "ALDN-206-U.mp4" in paths.storage_index_file.read_text(encoding="utf-8")
