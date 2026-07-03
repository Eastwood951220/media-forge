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
        step: str = "prepare"
        download_path: str = ""
        target_locations: list = None
        selected_storage_location: str = ""
        target_paths: list = None
        renamed_files: list = None
        moved_files: list = None
        skipped_files: list = None
        result: dict = None

        def __post_init__(self):
            if self.target_locations is None:
                self.target_locations = []
            if self.target_paths is None:
                self.target_paths = []
            if self.renamed_files is None:
                self.renamed_files = []
            if self.moved_files is None:
                self.moved_files = []
            if self.skipped_files is None:
                self.skipped_files = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self, subtask, config, provider):
            self.subtask = subtask
            self.config = config
            self.provider = provider
            self.messages = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
            write_storage_subtask_log(str(self.subtask.id), level, message, context or {})
            return {}

        def publish_subtask(self):
            pass

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


def test_execute_current_magnet_attempt_polls_until_file_appears(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass
    from pathlib import PurePosixPath
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    class Result:
        success = True
        error_message = None
        result_paths = []

    class File:
        name = "ABC-123.mp4"
        full_path = "/Downloads/storage_sub/ABC-123.mp4"
        size = 500 * 1024 * 1024
        is_directory = False
        is_search_result = False

    class PollingProvider:
        def __init__(self) -> None:
            self.list_calls = 0
            self.moved: list[tuple[list[str], str]] = []
            self.files = {}

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def list_files(self, path, force_refresh=False):
            if path.startswith("/Downloads/storage_"):
                self.list_calls += 1
                return [] if self.list_calls < 3 else [File()]
            return []

        def find_file(self, path):
            return self.files.get(path)

        def rename_file(self, old_path, new_name):
            return None

        def move_files(self, source_paths, target_folder):
            self.moved.append((source_paths, target_folder))
            for src in source_paths:
                from pathlib import PurePosixPath
                dst = str(PurePosixPath(target_folder) / PurePosixPath(src).name)
                self.files[dst] = File()
            return None

        def delete_file(self, path):
            return None

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-123"
        step: str = "prepare"
        download_path: str = ""
        target_locations: list = None
        selected_storage_location: str = ""
        target_paths: list = None
        renamed_files: list = None
        moved_files: list = None
        skipped_files: list = None
        result: dict = None

        def __post_init__(self):
            if self.target_locations is None:
                self.target_locations = []
            if self.target_paths is None:
                self.target_paths = []
            if self.renamed_files is None:
                self.renamed_files = []
            if self.moved_files is None:
                self.moved_files = []
            if self.skipped_files is None:
                self.skipped_files = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self, subtask, config, provider):
            self.subtask = subtask
            self.config = config
            self.provider = provider

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
            write_storage_subtask_log(str(self.subtask.id), level, message, context or {})
            return {}

        def publish_subtask(self):
            pass

    provider = PollingProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
            "download_max_poll_count": 5,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is True
    assert provider.list_calls == 3
    assert provider.moved == [(["/Downloads/storage_sub/ABC-123.mp4"], "/Movies/ABC-123")]


def test_execute_current_magnet_attempt_fails_after_download_poll_limit(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    class Result:
        success = True
        error_message = None
        result_paths = []

    class EmptyProvider:
        def __init__(self) -> None:
            self.list_calls = 0

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def list_files(self, path, force_refresh=False):
            if path.startswith("/Downloads/storage_"):
                self.list_calls += 1
            return []

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "ABC-404"
        step: str = "prepare"
        download_path: str = ""
        target_locations: list = None
        selected_storage_location: str = ""
        target_paths: list = None
        renamed_files: list = None
        moved_files: list = None
        skipped_files: list = None
        result: dict = None

        def __post_init__(self):
            if self.target_locations is None:
                self.target_locations = []
            if self.target_paths is None:
                self.target_paths = []
            if self.renamed_files is None:
                self.renamed_files = []
            if self.moved_files is None:
                self.moved_files = []
            if self.skipped_files is None:
                self.skipped_files = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self, subtask, config, provider):
            self.subtask = subtask
            self.config = config
            self.provider = provider

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
            write_storage_subtask_log(str(self.subtask.id), level, message, context or {})
            return {}

        def publish_subtask(self):
            pass

    provider = EmptyProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "download_max_poll_count": 3,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:abc", "tags": [], "weight": 10},
    )

    assert success is False
    assert provider.list_calls == 3
    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("轮询次数超过上限" in entry["message"] for entry in logs)
