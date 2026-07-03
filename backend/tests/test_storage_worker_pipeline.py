from dataclasses import dataclass

from backend.app.modules.storage.worker.file_finder import find_existing_video_files
from backend.app.modules.storage.worker.steps import select_main_videos


@dataclass
class FakeRemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False
    is_search_result: bool = False


class FakeProvider:
    def __init__(self) -> None:
        self.search_calls = []
        self.original_paths = {"/Search/ABC-123-C.mp4": "/Movies/A/ABC-123-C.mp4"}

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [FakeRemoteFile("ABC-123-C.mp4", "/Search/ABC-123-C.mp4", 500 * 1024 * 1024, False, True)]

    def get_original_path(self, path):
        return self.original_paths[path]

    def list_files(self, path, force_refresh=False):
        return []


def test_find_existing_video_files_uses_search_and_original_path() -> None:
    provider = FakeProvider()

    files = find_existing_video_files(
        provider,
        search_terms=["ABC-123"],
        search_paths=["/Downloads"],
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert files[0]["path"] == "/Movies/A/ABC-123-C.mp4"
    assert provider.search_calls == [("ABC-123", "/Downloads")]


def test_select_main_videos_requires_video_extension_and_min_size() -> None:
    files = [
        {"name": "small.mp4", "path": "/a/small.mp4", "size": 20 * 1024 * 1024},
        {"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024},
    ]

    selected = select_main_videos(files, {"video_extensions": [".mp4", ".mkv"], "minimum_video_size_mb": 100})

    assert selected == [{"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024}]


def test_execute_current_magnet_attempt_logs_submit_failure(tmp_path, monkeypatch):
    import uuid
    from dataclasses import dataclass
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    class FailingProvider:
        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("cloud-submit-failed")

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-FAIL"

    @dataclass
    class FakeContext:
        subtask: FakeSubtask
        config: dict
        provider: object

    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={"download_root_folder": "/Downloads", "video_extensions": [".mp4"], "minimum_video_size_mb": 100},
        provider=FailingProvider(),
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is False
    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("提交磁力失败" in entry["message"] for entry in logs)
