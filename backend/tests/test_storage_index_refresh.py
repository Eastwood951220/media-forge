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


def paths_for(tmp_path):
    return RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )


def test_full_refresh_builds_tree_index(tmp_path):
    paths = paths_for(tmp_path)

    class Provider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append(path)
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
        mode="full",
    )

    assert metadata.status == "completed"
    assert metadata.force_refresh_mode == "full"
    assert metadata.video_count == 1
    tree = StorageIndexStore(paths).read_index_tree()
    assert tree["categories"]["巨乳|熟女|BBW"]["code_folders"]["ALDN-206-U"]["videos"][0]["file_name"] == "ALDN-206-U.mp4"
    assert "/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U" in provider.calls


def test_incremental_refresh_skips_old_code_folder_videos_and_scans_new_folders(tmp_path):
    paths = paths_for(tmp_path)
    store = StorageIndexStore(paths)

    class FullProvider:
        def list_files(self, path, force_refresh=False):
            if path == "/Movies":
                return [RemoteFile("A", "/Movies/A", 0, True)]
            if path == "/Movies/A":
                return [RemoteFile("OLD-001", "/Movies/A/OLD-001", 0, True)]
            if path == "/Movies/A/OLD-001":
                return [RemoteFile("OLD-001.mp4", "/Movies/A/OLD-001/OLD-001.mp4", 500 * 1024 * 1024)]
            return []

    StorageIndexRefreshService(store).refresh(
        {"target_folder": "/Movies", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        FullProvider(),
        mode="full",
    )

    class IncrementalProvider:
        def __init__(self) -> None:
            self.calls = []

        def list_files(self, path, force_refresh=False):
            self.calls.append(path)
            if path == "/Movies":
                return [RemoteFile("A", "/Movies/A", 0, True)]
            if path == "/Movies/A":
                return [
                    RemoteFile("OLD-001", "/Movies/A/OLD-001", 0, True),
                    RemoteFile("NEW-002", "/Movies/A/NEW-002", 0, True),
                ]
            if path == "/Movies/A/NEW-002":
                return [RemoteFile("NEW-002.mp4", "/Movies/A/NEW-002/NEW-002.mp4", 500 * 1024 * 1024)]
            if path == "/Movies/A/OLD-001":
                raise AssertionError("incremental refresh must not scan old code folder videos")
            return []

    provider = IncrementalProvider()
    metadata = StorageIndexRefreshService(store).refresh(
        {"target_folder": "/Movies", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider,
        mode="incremental",
    )

    grouped = store.load_index_by_code()
    assert metadata.force_refresh_mode == "incremental"
    assert "OLD-001" in grouped
    assert "NEW-002" in grouped
    assert "/Movies/A/OLD-001" not in provider.calls
