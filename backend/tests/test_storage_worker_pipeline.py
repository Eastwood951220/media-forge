from dataclasses import dataclass
from types import SimpleNamespace

from backend.app.modules.storage.worker.file_finder import find_existing_video_files
from backend.app.modules.storage.worker.file_ops import select_main_videos


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
    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    class Result:
        success = True
        error_message = None
        result_paths = []

    class PollingProvider:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str]] = []
            self.list_calls: int = 0
            self.moved: list[tuple[list[str], str]] = []
            self.files = {}

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

        def get_original_path(self, path):
            return ""

        def list_files(self, path, force_refresh=False):
            self.list_calls += 1
            if path.startswith("/Downloads/storage_") and self.list_calls >= 3:
                return [type("File", (), {
                    "name": "ABC-123.mp4",
                    "full_path": f"{path}/ABC-123.mp4",
                    "size": 500 * 1024 * 1024,
                    "is_directory": False,
                    "is_search_result": False,
                })()]
            return []

        def find_file(self, path):
            return self.files.get(path)

        def rename_file(self, old_path, new_name):
            return None

        def move_files(self, source_paths, target_folder):
            self.moved.append((source_paths, target_folder))
            for src in source_paths:
                dst = str(PurePosixPath(target_folder) / PurePosixPath(src).name)
                self.files[dst] = type("File", (), {"size": 500 * 1024 * 1024})()
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


def test_execute_current_magnet_attempt_fails_after_download_poll_limit(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass
    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

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


def test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    target_folder = "/Movies/巨乳/MIDA-628"
    target_file = f"{target_folder}/MIDA-628.mp4"
    file_size = 6910439461

    class Result:
        success = True
        error_message = None
        result_paths = []

    class ExistingTargetProvider:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            return Result()

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def list_files(self, path, force_refresh=False):
            if path.startswith("/Downloads/storage_"):
                return [type("ListFile", (), {
                    "name": "MIDA-628.mp4",
                    "full_path": f"{path}/MIDA-628.mp4",
                    "size": file_size,
                    "is_directory": False,
                    "is_search_result": False,
                })()]
            return []

        def find_file(self, path):
            if path == target_file:
                return SimpleNamespace(size=file_size)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

        def delete_file(self, path):
            self.deleted.append(path)
            return SimpleNamespace(success=True)

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_code: str = "MIDA-628"
        step: str = "prepare"
        status: str = "running"
        skip_reason: str | None = None
        download_path: str = ""
        target_locations: list | None = None
        selected_storage_location: str = "巨乳"
        target_paths: list | None = None
        renamed_files: list | None = None
        moved_files: list | None = None
        skipped_files: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.target_locations is None:
                self.target_locations = ["巨乳"]
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

            write_storage_subtask_log(
                str(self.subtask.id),
                level,
                message,
                context or {},
                step=step,
                event=event,
            )
            return {}

        def publish_subtask(self):
            return None

    provider = ExistingTargetProvider()
    subtask = FakeSubtask(id=uuid.uuid4())
    context = FakeContext(
        subtask=subtask,
        config={
            "download_root_folder": "/Downloads",
            "target_folder": "/Movies",
            "download_max_poll_count": 1,
            "download_poll_interval_min": 0,
            "download_poll_interval_max": 0,
            "video_extensions": [".mp4"],
            "minimum_video_size_mb": 100,
            "use_task_subfolder": True,
        },
        provider=provider,
    )

    success = execute_current_magnet_attempt(
        context,
        {"id": "m1", "magnet_url": "magnet:?xt=urn:btih:mida628", "tags": [], "weight": 16394},
    )

    assert success is True
    assert subtask.status == "skipped"
    assert subtask.skip_reason == "target_exists"
    assert subtask.result["status"] == "skipped"
    assert subtask.result["reason"] == "target_exists"
    assert subtask.moved_files == []
    assert subtask.skipped_files[0]["skip_reason"] == "target_exists"
    assert subtask.skipped_files[0]["existing_targets"] == [target_file]
    assert provider.move_calls == []
    assert provider.copy_calls == []
    assert provider.deleted == [f"/Downloads/storage_{subtask.id}"]

    logs = read_storage_subtask_logs(str(subtask.id))
    assert any("目标文件已全部存在，子任务标记为跳过" in entry["message"] for entry in logs)
    assert any("清理完成" in entry["message"] for entry in logs)


def test_execute_subtask_pipeline_stops_after_target_exists_skip(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "target_exists"
        context.subtask.result = {"status": "skipped", "reason": "target_exists"}
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "MIDA-628"
        status: str = "queued"
        step: str = "prepare"
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts == [
        {
            "magnet_id": "m1",
            "success": True,
            "status": "skipped",
            "timestamp": context.subtask.magnet_attempts[0]["timestamp"],
        }
    ]


def test_is_rename_name_exists_error_detects_clouddrive_20004() -> None:
    from backend.app.modules.storage.worker.file_ops import is_rename_name_exists_error

    error = RuntimeError(
        'api error Cloud 115open(342367138) api error: code: 20004, '
        'message: 很抱歉，该目录名称已存在。'
    )

    assert is_rename_name_exists_error(error) is True
    assert is_rename_name_exists_error(RuntimeError("permission denied")) is False


def test_rename_name_exists_reuses_existing_canonical_source_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.rename_ops import rename_selected_videos

    class RenameNameExistsProvider:
        def __init__(self) -> None:
            self.find_calls: list[str] = []

        def rename_file(self, source_path, new_name):
            raise RuntimeError("api error: code: 20004, message: 很抱歉，该目录名称已存在。")

        def find_file(self, path):
            self.find_calls.append(path)
            if path == "/Downloads/MIDA-628.mp4":
                return SimpleNamespace(size=6910439461)
            return None

    class FakeSubtask:
        movie_code = "MIDA-628"

    class FakeContext:
        def __init__(self) -> None:
            self.subtask = FakeSubtask()
            self.provider = RenameNameExistsProvider()
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    renamed = rename_selected_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
            }
        ],
        tags=[],
    )

    assert renamed == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
        }
    ]
    assert context.provider.find_calls == ["/Downloads/MIDA-628.mp4"]
    assert any("重命名目标已存在，复用已有文件" in message for message in context.messages)


def test_rename_name_exists_without_resolved_file_becomes_terminal_skip() -> None:
    from backend.app.modules.storage.worker.move_ops import move_renamed_videos

    class Provider:
        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            return None

    class Subtask:
        pass

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.subtask = Subtask()
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "rename_error": "api error: code: 20004, message: 很抱歉，该目录名称已存在。",
                "rename_name_exists": True,
                "renamed_name": "MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628"],
    )

    assert result.moved_files == []
    assert result.skipped_files == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "rename_error": "api error: code: 20004, message: 很抱歉，该目录名称已存在。",
            "rename_name_exists": True,
            "renamed_name": "MIDA-628.mp4",
            "skip_reason": "rename_name_exists",
        }
    ]
    assert result.all_rename_name_exists is True
    assert any("跳过重命名目标已存在的文件" in message for message in context.messages)


def test_execute_subtask_pipeline_stops_after_rename_name_exists_skip(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "rename_name_exists"
        context.subtask.result = {"status": "skipped", "reason": "rename_name_exists"}
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "MIDA-628"
        status: str = "queued"
        step: str = "prepare"
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "rename_name_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "skipped"


def test_rename_existing_source_skips_when_single_target_already_has_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.move_ops import move_renamed_videos

    target_file = "/Movies/巨乳/MIDA-628/MIDA-628.mp4"

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path == target_file:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628"],
    )

    assert result.moved_files == []
    assert result.skipped_files == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
            "skip_reason": "target_exists",
            "existing_targets": [target_file],
        }
    ]
    assert result.all_targets_exist is True
    assert context.provider.move_calls == []
    assert context.provider.copy_calls == []
    assert any("跳过已存在: MIDA-628.mp4" in message for message in context.messages)


def test_rename_existing_source_skips_when_all_multi_targets_already_have_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.move_ops import move_renamed_videos

    target_files = {
        "/Movies/巨乳/MIDA-628/MIDA-628.mp4",
        "/Movies/中字/MIDA-628/MIDA-628.mp4",
    }

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path in target_files:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628", "/Movies/中字/MIDA-628"],
    )

    assert result.moved_files == []
    assert result.skipped_files[0]["skip_reason"] == "target_exists"
    assert result.skipped_files[0]["existing_targets"] == [
        "/Movies/巨乳/MIDA-628/MIDA-628.mp4",
        "/Movies/中字/MIDA-628/MIDA-628.mp4",
    ]
    assert result.all_targets_exist is True
    assert context.provider.move_calls == []
    assert context.provider.copy_calls == []


def test_rename_existing_source_copies_missing_multi_target_and_keeps_existing_move_target() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.move_ops import move_renamed_videos

    existing_move_target = "/Movies/中字/MIDA-628/MIDA-628.mp4"

    class Provider:
        def __init__(self) -> None:
            self.move_calls: list[tuple[list[str], str]] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            if path == existing_move_target:
                return SimpleNamespace(size=6910439461)
            return None

        def move_files(self, source_paths, target_folder):
            self.move_calls.append((source_paths, target_folder))
            return None

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            return None

    class FakeContext:
        def __init__(self) -> None:
            self.provider = Provider()
            self.config = {"auto_create_target_folder": True}
            self.messages: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.messages.append(message)
            return {}

    context = FakeContext()

    result = move_renamed_videos(
        context,
        [
            {
                "name": "hhd800.com@MIDA-628.mp4",
                "path": "/Downloads/hhd800.com@MIDA-628.mp4",
                "size": 6910439461,
                "renamed_path": "/Downloads/MIDA-628.mp4",
                "renamed_name": "MIDA-628.mp4",
                "rename_name_exists": True,
                "existing_path": "/Downloads/MIDA-628.mp4",
            }
        ],
        ["/Movies/巨乳/MIDA-628", "/Movies/中字/MIDA-628"],
    )

    assert result.all_targets_exist is False
    assert result.moved_files == [
        {
            "name": "hhd800.com@MIDA-628.mp4",
            "path": "/Downloads/hhd800.com@MIDA-628.mp4",
            "size": 6910439461,
            "renamed_path": "/Downloads/MIDA-628.mp4",
            "renamed_name": "MIDA-628.mp4",
            "rename_name_exists": True,
            "existing_path": "/Downloads/MIDA-628.mp4",
            "moved_path": "/Movies/中字/MIDA-628/MIDA-628.mp4",
            "copied_paths": ["/Movies/巨乳/MIDA-628/MIDA-628.mp4"],
        }
    ]
    assert result.skipped_files == []
    assert context.provider.copy_calls == [
        ("/Downloads/MIDA-628.mp4", "/Movies/巨乳/MIDA-628")
    ]
    assert context.provider.move_calls == []


def test_execute_subtask_pipeline_stops_after_rename_existing_source_target_skip(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "target_exists"
        context.subtask.result = {
            "status": "skipped",
            "reason": "target_exists",
            "files": [
                {
                    "renamed_path": "/Downloads/MIDA-628.mp4",
                    "existing_targets": ["/Movies/巨乳/MIDA-628/MIDA-628.mp4"],
                    "skip_reason": "target_exists",
                }
            ],
        }
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "MIDA-628"
        status: str = "queued"
        step: str = "prepare"
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "skipped"


def test_poll_downloaded_video_files_uses_list_subfiles_and_does_not_search_root(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.download import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return [RemoteFile("ACZD-165", "/Downloads/storage_sub/ACZD-165", 0, True)]
            if path == "/Downloads/storage_sub/ACZD-165":
                return [
                    RemoteFile(
                        "hhd800.com@ACZD-165.mp4",
                        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                        500 * 1024 * 1024,
                    )
                ]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 2,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert [file["path"] for file in files] == [
        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4"
    ]
    assert context.provider.search_calls == []
    assert context.provider.list_calls == [
        "/Downloads/storage_sub",
        "/Downloads/storage_sub/ACZD-165",
    ]
    assert [log["context"]["search_method"] for log in context.logs if log["message"] == "查找下载文件"] == [
        "list_sub_files",
    ]


def test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.download import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 500 * 1024 * 1024)]

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 3,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert [file["path"] for file in files] == ["/Downloads/storage_sub/ACZD-165.mp4"]
    assert context.provider.search_calls == []
    assert context.provider.list_calls == ["/Downloads/storage_sub"]


def test_poll_downloaded_video_files_does_not_search_download_root_after_poll_exhaustion(monkeypatch):
    from backend.app.modules.storage.worker.download import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_max_poll_count": 2,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = poll_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert files == []
    assert context.provider.search_calls == []
    assert context.provider.list_calls == ["/Downloads/storage_sub", "/Downloads/storage_sub"]
    assert context.logs[-1]["message"] == "轮询次数超过上限: 2/2，任务目录未发现可用视频文件，跳过当前磁力"


def test_subtask_pipeline_starts_next_magnet_only_after_current_failure(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_order: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_order.append(magnet["id"])
        return magnet["id"] == "m2"

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_order == ["m1", "m2"]
    assert context.subtask.status == "completed"
    assert [attempt["magnet_id"] for attempt in context.subtask.magnet_attempts] == ["m1", "m2"]
    assert [attempt["success"] for attempt in context.subtask.magnet_attempts] == [False, True]


def test_subtask_pipeline_does_not_start_later_magnet_after_success(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_order: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_order.append(magnet["id"])
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_order == ["m1"]
    assert context.subtask.status == "completed"
    assert [attempt["magnet_id"] for attempt in context.subtask.magnet_attempts] == ["m1"]


def test_deduped_single_real_file_renames_without_cd_suffix() -> None:
    from backend.app.modules.storage.tasks.policies import build_video_filename

    accepted_files = [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        }
    ]

    new_name = build_video_filename(
        movie_code="ACZD-165",
        original_name=accepted_files[0]["name"],
        tags=[],
        index=0,
        total=len(accepted_files),
    )

    assert new_name == "ACZD-165.mp4"


def test_scan_found_files_rejects_virtual_search_paths() -> None:
    from backend.app.modules.storage.worker.file_ops import scan_found_files

    scanned = scan_found_files([
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        },
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        },
    ])

    assert scanned == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        }
    ]


def test_execute_current_magnet_attempt_uses_recovery_only_when_submit_task_exists(monkeypatch):
    import uuid
    from dataclasses import dataclass
    from pathlib import PurePosixPath

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []
            self.renamed: list[tuple[str, str]] = []
            self.moved: list[tuple[list[str], str]] = []
            self.deleted: list[str] = []
            self.files: dict[str, RemoteFile] = {}

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return [
                    RemoteFile("ACZD-165", "/Downloads/storage_sub/ACZD-165", 0, True),
                ]
            if path == "/Downloads/storage_sub/ACZD-165":
                return [
                    RemoteFile(
                        "hhd800.com@ACZD-165.mp4",
                        "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                        500 * 1024 * 1024,
                    )
                ]
            if path == "/Movies/A/ACZD-165":
                return []
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

        def find_file(self, path):
            if path in self.files:
                return self.files[path]
            return None

        def rename_file(self, old_path, new_name):
            self.renamed.append((old_path, new_name))

        def move_files(self, source_paths, target_folder):
            self.moved.append((source_paths, target_folder))
            for src in source_paths:
                dst = str(PurePosixPath(target_folder) / PurePosixPath(src).name)
                self.files[dst] = RemoteFile(PurePosixPath(dst).name, dst, 500 * 1024 * 1024)

        def delete_file(self, path):
            self.deleted.append(path)

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is True
    assert context.provider.search_calls == []
    assert "/Downloads/storage_sub" in context.provider.list_calls
    assert context.provider.renamed == [
        ("/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4", "ACZD-165.mp4")
    ]
    assert context.provider.moved == [
        (["/Downloads/storage_sub/ACZD-165/ACZD-165.mp4"], "/Movies/A/ACZD-165")
    ]
    assert any(log["context"].get("search_scope") == "recovery_task_download_folder" for log in context.logs)


def test_recover_existing_downloaded_video_files_searches_root_after_task_folder_empty() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.download import recover_existing_downloaded_video_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []
            self.original_path_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return [
                RemoteFile(
                    "hhd800.com@ACZD-165.mp4",
                    "/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
                    500 * 1024 * 1024,
                    False,
                    True,
                )
            ]

        def get_original_path(self, path):
            self.original_path_calls.append(path)
            return "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4"

    class Subtask:
        movie_code = "ACZD-165"

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
            }
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()

    files = recover_existing_downloaded_video_files(
        context,
        search_terms=["ACZD-165"],
        task_download_folder="/Downloads/storage_sub",
        download_root="/Downloads",
    )

    assert files == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
            "is_dir": False,
        }
    ]
    assert "/Downloads/storage_sub" in context.provider.list_calls
    assert context.provider.search_calls == [("ACZD-165", "/Downloads")]
    assert context.provider.original_path_calls == ["/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4"]
    assert context.logs[0]["context"]["search_scope"] == "recovery_download_root"
    assert context.logs[0]["context"]["original_path_results"] == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "raw_path": "/Downloads/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
            "original_path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
        }
    ]


def test_find_existing_target_files_uses_list_files_for_single_target() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.target_files import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.find_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/人妖/ACZD-165":
                return [
                    RemoteFile("ACZD-165.mp4", "/Movies/人妖/ACZD-165/ACZD-165.mp4", 4770615244),
                ]
            return []

        def find_file(self, path):
            self.find_calls.append(path)
            return None

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/人妖/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.all_targets_exist is True
    assert result.existing_targets == ["/Movies/人妖/ACZD-165"]
    assert result.missing_targets == []
    assert result.checked_targets == ["/Movies/人妖/ACZD-165"]


def test_find_existing_target_files_requires_all_targets_to_exist() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.target_files import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 4770615244)]
            return []

    provider = Provider()

    result = find_existing_target_files(
        provider=provider,
        target_paths=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.all_targets_exist is False
    assert result.existing_targets == ["/Movies/A/ACZD-165"]
    assert result.missing_targets == ["/Movies/B/ACZD-165"]
    assert provider.list_calls == ["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"]


def test_find_existing_target_files_accepts_suffix_filename() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.target_files import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def list_files(self, path, force_refresh=False):
            return [
                RemoteFile("ACZD-165-C.mp4", f"{path}/ACZD-165-C.mp4", 4770615244),
            ]

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/A/ACZD-165-C"],
        expected_names=["ACZD-165-C.mp4", "ACZD-165.mp4"],
    )

    assert result.all_targets_exist is True
    assert result.existing_targets == ["/Movies/A/ACZD-165-C"]


def test_execute_current_magnet_attempt_skips_after_task_exists_when_target_file_exists(monkeypatch) -> None:
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.search_calls: list[tuple[str, str]] = []
            self.submit_calls = 0

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            self.submit_calls += 1
            raise RuntimeError("api error: code: 10008, message: 任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [
                    RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 4770615244),
                ]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return []

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}
        skip_reason = None

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is True
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.result == {
        "status": "skipped",
        "reason": "target_exists",
        "files": [
            {
                "name": "ACZD-165.mp4",
                "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
                "skip_reason": "target_exists",
            }
        ],
    }
    assert context.subtask.skipped_files == [
        {
            "name": "ACZD-165.mp4",
            "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
            "skip_reason": "target_exists",
        }
    ]
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert any(log["event"] == "subtask_skipped" for log in context.logs)


def test_execute_current_magnet_attempt_skips_after_task_exists_only_when_all_targets_exist(monkeypatch) -> None:
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path in {"/Movies/A/ACZD-165", "/Movies/B/ACZD-165"}:
                return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 4770615244)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A", "B"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}
        skip_reason = None

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is True
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert sorted(context.subtask.skipped_files[0]["existing_targets"]) == [
        "/Movies/A/ACZD-165/ACZD-165.mp4",
        "/Movies/B/ACZD-165/ACZD-165.mp4",
    ]
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert "/Movies/B/ACZD-165" in context.provider.list_calls


def test_execute_current_magnet_attempt_does_not_skip_after_task_exists_when_any_target_missing(monkeypatch) -> None:
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("任务已存在")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 4770615244)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        target_locations = ["A", "B"]
        selected_storage_location = None
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "queued"
        step = "prepare"
        result = {}
        skip_reason = None

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is False
    assert context.subtask.status == "queued"
    assert context.subtask.skip_reason is None
    assert "/Movies/A/ACZD-165" in context.provider.list_calls
    assert "/Movies/B/ACZD-165" in context.provider.list_calls
    assert any(
        log["message"] == "检查目标目录是否已存在视频文件"
        and log["context"]["missing_targets"] == ["/Movies/B/ACZD-165"]
        for log in context.logs
    )


def test_subtask_pipeline_stops_after_existing_target_skip_from_task_exists(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_ids.append(magnet["id"])
        context.subtask.status = "skipped"
        context.subtask.skip_reason = "target_exists"
        context.subtask.result = {
            "status": "skipped",
            "reason": "target_exists",
            "files": [
                {
                    "renamed_name": "ACZD-165.mp4",
                    "existing_targets": ["/Movies/A/ACZD-165/ACZD-165.mp4"],
                    "skip_reason": "target_exists",
                }
            ],
        }
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "skipped"
    assert context.subtask.skip_reason == "target_exists"
    assert context.subtask.step == "done"
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "skipped"


def test_find_existing_target_files_reports_source_and_missing_targets() -> None:
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.target_files import find_existing_target_files

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Movies/A/ACZD-165":
                return [
                    RemoteFile(
                        name="ACZD-165.mp4",
                        full_path="/Movies/A/ACZD-165/ACZD-165.mp4",
                        size=500 * 1024 * 1024,
                    )
                ]
            if path == "/Movies/B/ACZD-165":
                return []
            return []

    result = find_existing_target_files(
        provider=Provider(),
        target_paths=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
    )

    assert result.any_target_exists is True
    assert result.all_targets_exist is False
    assert result.checked_targets == ["/Movies/A/ACZD-165", "/Movies/B/ACZD-165"]
    assert result.existing_targets == ["/Movies/A/ACZD-165"]
    assert result.missing_targets == ["/Movies/B/ACZD-165"]
    assert result.source_path == "/Movies/A/ACZD-165/ACZD-165.mp4"
    assert result.source_name == "ACZD-165.mp4"
    assert result.existing_files == [
        {
            "target_folder": "/Movies/A/ACZD-165",
            "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "name": "ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
        }
    ]


def test_copy_existing_target_to_missing_targets_copies_from_first_found_target() -> None:
    from backend.app.modules.storage.worker.target_files import (
        ExistingTargetFilesResult,
        copy_existing_target_to_missing_targets,
    )

    class Provider:
        def __init__(self) -> None:
            self.ensure_calls: list[str] = []
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            self.ensure_calls.append(path)

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.logs: list[dict] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

    context = Context()
    result = ExistingTargetFilesResult(
        all_targets_exist=False,
        any_target_exists=True,
        checked_targets=["/Movies/A/ACZD-165", "/Movies/B/ACZD-165", "/Movies/C/ACZD-165"],
        existing_targets=["/Movies/A/ACZD-165"],
        missing_targets=["/Movies/B/ACZD-165", "/Movies/C/ACZD-165"],
        expected_names=["ACZD-165.mp4"],
        existing_files=[
            {
                "target_folder": "/Movies/A/ACZD-165",
                "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
                "name": "ACZD-165.mp4",
                "size": 500 * 1024 * 1024,
            }
        ],
        source_path="/Movies/A/ACZD-165/ACZD-165.mp4",
        source_name="ACZD-165.mp4",
        source_size=500 * 1024 * 1024,
    )

    copied = copy_existing_target_to_missing_targets(context, result)

    assert context.provider.ensure_calls == ["/Movies/B/ACZD-165", "/Movies/C/ACZD-165"]
    assert context.provider.copy_calls == [
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/B/ACZD-165"),
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/C/ACZD-165"),
    ]
    assert copied == [
        {
            "name": "ACZD-165.mp4",
            "path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "size": 500 * 1024 * 1024,
            "renamed_name": "ACZD-165.mp4",
            "moved_path": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "copied_paths": ["/Movies/B/ACZD-165/ACZD-165.mp4", "/Movies/C/ACZD-165/ACZD-165.mp4"],
            "copy_source": "/Movies/A/ACZD-165/ACZD-165.mp4",
            "copy_source_target": "/Movies/A/ACZD-165",
        }
    ]
    assert any("已从命中的目标文件复制到缺失目标" in log["message"] for log in context.logs)


def test_execute_current_magnet_attempt_copies_from_existing_target_when_multiple_mode_partial_targets(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.list_calls: list[str] = []
            self.copy_calls: list[tuple[str, str]] = []
            self.ensure_calls: list[str] = []
            self.deleted: list[str] = []
            self.files = {
                "/Movies/A/ACZD-165/ACZD-165.mp4": RemoteFile(
                    "ACZD-165.mp4",
                    "/Movies/A/ACZD-165/ACZD-165.mp4",
                    500 * 1024 * 1024,
                )
            }

        def ensure_directory(self, path):
            self.ensure_calls.append(path)

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("磁力链接已存在 (code 10008)")

        def list_files(self, path, force_refresh=False):
            self.list_calls.append(path)
            if path == "/Downloads/storage_sub":
                return []
            if path == "/Downloads":
                return []
            if path == "/Movies/A/ACZD-165":
                return [self.files["/Movies/A/ACZD-165/ACZD-165.mp4"]]
            if path == "/Movies/B/ACZD-165":
                return []
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))
            dest_path = f"{dest_folder}/ACZD-165.mp4"
            self.files[dest_path] = RemoteFile("ACZD-165.mp4", dest_path, 500 * 1024 * 1024)

        def find_file(self, path):
            return self.files.get(path)

        def delete_file(self, path):
            self.deleted.append(path)

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        storage_mode = "multiple"
        target_locations = ["A", "B"]
        selected_storage_location = ""
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "running"
        step = "prepare"
        result = {}
        skip_reason = None

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []
            self.publish_count = 0

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            self.publish_count += 1

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is True
    assert context.subtask.result["status"] == "success"
    assert context.subtask.result["reason"] == "copied_from_existing_target"
    assert context.subtask.moved_files[0]["copy_source"] == "/Movies/A/ACZD-165/ACZD-165.mp4"
    assert context.provider.copy_calls == [
        ("/Movies/A/ACZD-165/ACZD-165.mp4", "/Movies/B/ACZD-165")
    ]
    assert context.provider.find_file("/Movies/B/ACZD-165/ACZD-165.mp4") is not None
    assert context.provider.deleted == ["/Downloads/storage_sub"]
    assert any(log["message"] == "检查目标目录是否已存在视频文件" for log in context.logs)
    assert any(log["message"] == "磁力任务处理成功" for log in context.logs)


def test_execute_current_magnet_attempt_does_not_copy_between_targets_in_single_mode(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setattr("backend.app.modules.storage.worker.download.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False

    class Provider:
        def __init__(self) -> None:
            self.copy_calls: list[tuple[str, str]] = []

        def ensure_directory(self, path):
            return None

        def submit_offline_download(self, magnet_url, target_folder):
            raise RuntimeError("磁力链接已存在 (code 10008)")

        def list_files(self, path, force_refresh=False):
            if path == "/Movies/A/ACZD-165":
                return [RemoteFile("ACZD-165.mp4", "/Movies/A/ACZD-165/ACZD-165.mp4", 500 * 1024 * 1024)]
            return []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            return []

        def copy_file(self, source_path, dest_folder):
            self.copy_calls.append((source_path, dest_folder))

        def find_file(self, path):
            return None

        def delete_file(self, path):
            return None

    class Subtask:
        id = "sub"
        movie_id = uuid.uuid4()
        movie_code = "ACZD-165"
        storage_mode = "single"
        target_locations = ["A", "B"]
        selected_storage_location = ""
        download_path = ""
        target_paths = []
        renamed_files = []
        moved_files = []
        skipped_files = []
        status = "running"
        step = "prepare"
        result = {}
        skip_reason = None

    class Context:
        def __init__(self) -> None:
            self.provider = Provider()
            self.subtask = Subtask()
            self.config = {
                "download_root_folder": "/Downloads",
                "target_folder": "/Movies",
                "download_max_poll_count": 1,
                "download_poll_interval_min": 0,
                "download_poll_interval_max": 0,
                "video_extensions": [".mp4"],
                "minimum_video_size_mb": 100,
                "use_task_subfolder": True,
                "auto_create_target_folder": True,
            }
            self.logs: list[dict] = []

        def set_step(self, step):
            self.subtask.step = step

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append({"level": level, "message": message, "context": context or {}, "step": step, "event": event})
            return {}

        def publish_subtask(self):
            return None

    context = Context()

    success = execute_current_magnet_attempt(
        context,
        {
            "id": "m1",
            "magnet_url": "magnet:?xt=urn:btih:first",
            "tags": [],
            "weight": 100,
            "selected": True,
        },
    )

    assert success is False
    assert context.provider.copy_calls == []
    assert context.subtask.result == {}


def test_execute_subtask_pipeline_stops_after_existing_target_copy_success(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_ids: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        attempt_ids.append(magnet["id"])
        context.subtask.result = {"status": "success", "reason": "copied_from_existing_target"}
        context.subtask.moved_files = [
            {
                "name": "ACZD-165.mp4",
                "moved_path": "/Movies/A/ACZD-165/ACZD-165.mp4",
                "copied_paths": ["/Movies/B/ACZD-165/ACZD-165.mp4"],
            }
        ]
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        magnets = [
            FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True),
            FakeMagnet("m2", "magnet:?xt=urn:btih:second", [], 90, False),
        ]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "ACZD-165"
        status: str = "queued"
        step: str = "prepare"
        skip_reason: str | None = None
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None
        moved_files: list | None = None

        def __post_init__(self):
            if self.magnet_attempts is None:
                self.magnet_attempts = []
            if self.result is None:
                self.result = {}
            if self.moved_files is None:
                self.moved_files = []

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 2}
            self.logs: list[str] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append(message)
            return {}

        def publish_subtask(self):
            return None

    context = FakeContext()

    execute_subtask_pipeline(context)

    assert attempt_ids == ["m1"]
    assert context.subtask.status == "completed"
    assert context.subtask.step == "done"
    assert context.subtask.result == {"status": "success", "reason": "copied_from_existing_target"}
    assert context.subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert context.subtask.magnet_attempts[0]["success"] is True
    assert context.subtask.magnet_attempts[0]["status"] == "running"


def test_is_submit_task_exists_error_matches_clouddrive_duplicate_messages() -> None:
    from backend.app.modules.storage.worker.download import is_submit_task_exists_error

    assert is_submit_task_exists_error(RuntimeError("10008 task exists")) is True
    assert is_submit_task_exists_error("任务已存在") is True
    assert is_submit_task_exists_error(RuntimeError("network down")) is False


def test_storage_file_operation_modules_export_current_public_functions() -> None:
    from backend.app.modules.storage.worker import cleanup_ops, file_ops, move_ops, rename_ops, verify_ops

    assert rename_ops.is_rename_name_exists_error("名称已存在")
    assert callable(rename_ops.rename_selected_videos)
    assert callable(move_ops.move_renamed_videos)
    assert callable(verify_ops.verify_moved_files)
    assert callable(cleanup_ops.cleanup_download_folder)
    assert file_ops.rename_selected_videos is rename_ops.rename_selected_videos
    assert file_ops.move_renamed_videos is move_ops.move_renamed_videos
    assert file_ops.verify_moved_files is verify_ops.verify_moved_files
    assert file_ops.cleanup_download_folder is cleanup_ops.cleanup_download_folder


def test_plan_storage_attempt_uses_selected_storage_location() -> None:
    import uuid
    from types import SimpleNamespace
    from backend.app.modules.storage.worker.target_planning import plan_storage_attempt

    subtask = SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000123"),
        movie_code="ABC-123",
        target_locations=["A", "B"],
        selected_storage_location="B",
        download_path="",
        target_paths=[],
    )

    plan = plan_storage_attempt(
        subtask,
        {"download_root_folder": "/Downloads", "target_folder": "/Movies"},
        {"id": "m1", "tags": ["中字"]},
    )

    assert plan.download_folder == "/Downloads/storage_00000000-0000-0000-0000-000000000123"
    assert plan.target_paths == ["/Movies/B/ABC-123-C"]
    assert subtask.download_path == plan.download_folder
    assert subtask.target_paths == plan.target_paths


def test_append_magnet_attempt_records_status_and_success() -> None:
    from types import SimpleNamespace
    from backend.app.modules.storage.worker.attempts import append_magnet_attempt

    subtask = SimpleNamespace(status="running", magnet_attempts=None)

    append_magnet_attempt(subtask, {"id": "m1"}, success=False)

    assert subtask.magnet_attempts[0]["magnet_id"] == "m1"
    assert subtask.magnet_attempts[0]["success"] is False
    assert subtask.magnet_attempts[0]["status"] == "running"


def test_storage_attempt_flow_modules_export_public_functions() -> None:
    from backend.app.modules.storage.worker.download_flow import DownloadFlowResult, run_download_flow
    from backend.app.modules.storage.worker.existing_target_flow import handle_existing_target_fallback
    from backend.app.modules.storage.worker.file_pipeline import run_found_files_pipeline

    assert DownloadFlowResult(found_files=[], submit_task_exists=False).found_files == []
    assert callable(run_download_flow)
    assert callable(handle_existing_target_fallback)
    assert callable(run_found_files_pipeline)


def test_is_vr_movie_tags_matches_only_clear_vr_tags() -> None:
    from backend.app.modules.storage.tasks.policies import is_vr_movie_tags

    assert is_vr_movie_tags(["VR"]) is True
    assert is_vr_movie_tags(["vr"]) is True
    assert is_vr_movie_tags(["VR影片"]) is True
    assert is_vr_movie_tags(["巨乳", "中文字幕"]) is False
    assert is_vr_movie_tags(["preview", "driver"]) is False
    assert is_vr_movie_tags(["", None, 123]) is False


def test_insert_vr_directory_before_code_folder_without_duplication() -> None:
    from backend.app.modules.storage.tasks.policies import insert_vr_directory

    assert (
        insert_vr_directory("/Movies/日本/巨乳/XXX", "XXX")
        == "/Movies/日本/巨乳/VR/XXX"
    )
    assert (
        insert_vr_directory("/Movies/日本/巨乳/VR/XXX", "XXX")
        == "/Movies/日本/巨乳/VR/XXX"
    )
    assert insert_vr_directory("/Movies/XXX", "XXX") == "/Movies/VR/XXX"


def test_quality_dedupe_key_removes_quality_tokens_but_preserves_parts() -> None:
    from backend.app.modules.storage.tasks.policies import quality_dedupe_key

    assert quality_dedupe_key("XXX_1_8K.mp4") == quality_dedupe_key("XXX_1_HD.mp4")
    assert quality_dedupe_key("XXX-CD1.mp4") != quality_dedupe_key("XXX-CD2.mp4")
    assert quality_dedupe_key("XXX_part1_4K.mp4") != quality_dedupe_key("XXX_part2_4K.mp4")


def test_dedupe_quality_variants_keeps_largest_per_group() -> None:
    from backend.app.modules.storage.tasks.policies import dedupe_quality_variants

    videos = [
        {"name": "XXX_1_HD.mp4", "path": "/Downloads/XXX_1_HD.mp4", "size": 100},
        {"name": "XXX_1_8K.mp4", "path": "/Downloads/XXX_1_8K.mp4", "size": 300},
        {"name": "XXX-CD1.mp4", "path": "/Downloads/XXX-CD1.mp4", "size": 200},
        {"name": "XXX-CD2.mp4", "path": "/Downloads/XXX-CD2.mp4", "size": 250},
    ]

    kept, dropped = dedupe_quality_variants(videos)

    assert [item["name"] for item in kept] == ["XXX_1_8K.mp4", "XXX-CD1.mp4", "XXX-CD2.mp4"]
    assert dropped == [
        {
            "name": "XXX_1_HD.mp4",
            "path": "/Downloads/XXX_1_HD.mp4",
            "size": 100,
            "dedupe_group_key": "xxx_1",
            "kept_name": "XXX_1_8K.mp4",
            "reason": "duplicate_quality_smaller_size",
        }
    ]


def test_plan_storage_attempt_inserts_vr_for_movie_tags_only() -> None:
    import uuid
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.target_planning import plan_storage_attempt

    subtask = SimpleNamespace(
        id=uuid.uuid4(),
        movie_code="XXX",
        target_locations=["日本/巨乳"],
        selected_storage_location=None,
        download_path="",
        target_paths=[],
    )

    plan = plan_storage_attempt(
        subtask,
        {"download_root_folder": "/Downloads", "target_folder": "/Movies"},
        {"tags": ["VR"]},
        movie_tags=["VR"],
    )

    assert plan.target_paths == ["/Movies/日本/巨乳/VR/XXX"]
    assert subtask.target_paths == ["/Movies/日本/巨乳/VR/XXX"]


def test_plan_storage_attempt_ignores_magnet_vr_tags_for_target_path() -> None:
    import uuid
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.target_planning import plan_storage_attempt

    subtask = SimpleNamespace(
        id=uuid.uuid4(),
        movie_code="XXX",
        target_locations=["日本/巨乳"],
        selected_storage_location=None,
        download_path="",
        target_paths=[],
    )

    plan = plan_storage_attempt(
        subtask,
        {"download_root_folder": "/Downloads", "target_folder": "/Movies"},
        {"tags": ["VR"]},
        movie_tags=[],
    )

    assert plan.target_paths == ["/Movies/日本/巨乳/XXX"]


def test_plan_storage_attempt_vr_multiple_targets_without_duplicate_vr() -> None:
    import uuid
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.target_planning import plan_storage_attempt

    subtask = SimpleNamespace(
        id=uuid.uuid4(),
        movie_code="XXX",
        target_locations=["日本/巨乳", "日本/VR"],
        selected_storage_location=None,
        download_path="",
        target_paths=[],
    )

    plan = plan_storage_attempt(
        subtask,
        {"download_root_folder": "/Downloads", "target_folder": "/Movies"},
        {"tags": []},
        movie_tags=["VR"],
    )

    assert plan.target_paths == ["/Movies/日本/巨乳/VR/XXX", "/Movies/日本/VR/XXX"]


def test_execute_subtask_pipeline_passes_movie_tags_to_attempt(monkeypatch) -> None:
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    observed_movie_tags: list[str] | None = None

    def fake_execute_current_magnet_attempt(context, magnet, movie_tags=None):
        nonlocal observed_movie_tags
        observed_movie_tags = movie_tags
        return True

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.steps.execute_current_magnet_attempt",
        fake_execute_current_magnet_attempt,
    )

    @dataclass
    class FakeMagnet:
        id: str
        magnet_url: str
        tags: list[str]
        weight: int
        selected: bool

    class FakeMovie:
        tags = []
        tags = ["VR", "巨乳"]
        magnets = [FakeMagnet("m1", "magnet:?xt=urn:btih:first", [], 100, True)]

    class FakeDb:
        def get(self, model, movie_id):
            return FakeMovie()

    @dataclass
    class FakeSubtask:
        id: uuid.UUID
        movie_id: uuid.UUID
        movie_code: str = "XXX"
        status: str = "queued"
        step: str = "prepare"
        started_at: object | None = None
        finished_at: object | None = None
        error_message: str | None = None
        current_magnet_id: str | None = None
        current_magnet_url: str = ""
        magnet_attempts: list | None = None
        result: dict | None = None

        def __post_init__(self):
            self.magnet_attempts = [] if self.magnet_attempts is None else self.magnet_attempts
            self.result = {} if self.result is None else self.result

    class FakeContext:
        def __init__(self) -> None:
            self.db = FakeDb()
            self.subtask = FakeSubtask(id=uuid.uuid4(), movie_id=uuid.uuid4())
            self.config = {"magnet_max_attempts_per_subtask": 1}

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

        def publish_subtask(self):
            return None

    execute_subtask_pipeline(FakeContext())

    assert observed_movie_tags == ["VR", "巨乳"]


def test_run_found_files_pipeline_dedupes_quality_variants_before_rename(monkeypatch) -> None:
    import uuid
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.file_pipeline import run_found_files_pipeline

    renamed_inputs: list[list[dict]] = []

    def fake_rename_selected_videos(context, selected_videos, tags):
        renamed_inputs.append(selected_videos)
        return [
            {
                **selected_videos[0],
                "renamed_path": selected_videos[0]["path"],
                "renamed_name": "XXX.mp4",
            }
        ]

    monkeypatch.setattr(
        "backend.app.modules.storage.worker.file_pipeline.rename_selected_videos",
        fake_rename_selected_videos,
    )
    monkeypatch.setattr(
        "backend.app.modules.storage.worker.file_pipeline.verify_moved_files",
        lambda context, moved_files: True,
    )
    monkeypatch.setattr(
        "backend.app.modules.storage.worker.file_pipeline.cleanup_download_folder",
        lambda context, download_folder, config: None,
    )

    class Provider:
        def ensure_directory(self, path):
            return None

        def find_file(self, path):
            return None

        def move_files(self, sources, target):
            return None

    class Context:
        def __init__(self) -> None:
            self.subtask = SimpleNamespace(
                id=uuid.uuid4(),
                movie_id=uuid.uuid4(),
                movie_code="XXX",
                renamed_files=[],
                moved_files=[],
                skipped_files=[],
                result={},
            )
            self.config = {"auto_create_target_folder": False}
            self.provider = Provider()
            self.logs: list[tuple[str, dict]] = []

        def log(self, level, message, context=None, *, step=None, event=None):
            self.logs.append((message, context or {}))
            return {}

        def set_step(self, step):
            self.subtask.step = step

        def publish_subtask(self):
            return None

    context = Context()

    success = run_found_files_pipeline(
        context,
        {"id": "m1", "tags": []},
        [
            {"name": "XXX_1_HD.mp4", "path": "/Downloads/XXX_1_HD.mp4", "size": 100 * 1024 * 1024, "is_dir": False},
            {"name": "XXX_1_8K.mp4", "path": "/Downloads/XXX_1_8K.mp4", "size": 300 * 1024 * 1024, "is_dir": False},
        ],
        ["/Movies/VR/XXX"],
        "/Downloads/storage_task",
        {"video_extensions": [".mp4"], "minimum_video_size_mb": 1},
    )

    assert success is True
    assert [item["name"] for item in renamed_inputs[0]] == ["XXX_1_8K.mp4"]
    assert any(
        payload.get("dropped_files", [{}])[0].get("reason") == "duplicate_quality_smaller_size"
        for _message, payload in context.logs
        if payload.get("dropped_files")
    )


def test_rename_selected_videos_orders_similar_numeric_parts_before_assigning_cd() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.rename_ops import rename_selected_videos

    class Provider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def rename_file(self, source_path, new_name):
            self.calls.append((source_path, new_name))

    class Context:
        def __init__(self) -> None:
            self.subtask = SimpleNamespace(movie_code="VRKM-1668")
            self.provider = Provider()

        def log(self, level, message, context=None, *, step=None, event=None):
            return {}

    context = Context()
    videos = [
        {
            "name": "4k2.com@vrkm01668_10_12000.mp4",
            "path": "/Downloads/4k2.com@vrkm01668_10_12000.mp4",
            "size": 1000,
        },
        {
            "name": "4k2.com@vrkm01668_1_12000.mp4",
            "path": "/Downloads/4k2.com@vrkm01668_1_12000.mp4",
            "size": 1000,
        },
        {
            "name": "4k2.com@vrkm01668_2_12000.mp4",
            "path": "/Downloads/4k2.com@vrkm01668_2_12000.mp4",
            "size": 1000,
        },
    ]

    renamed = rename_selected_videos(context, videos, tags=[])

    assert [item["name"] for item in renamed] == [
        "4k2.com@vrkm01668_1_12000.mp4",
        "4k2.com@vrkm01668_2_12000.mp4",
        "4k2.com@vrkm01668_10_12000.mp4",
    ]
    assert [item["renamed_name"] for item in renamed] == [
        "VRKM-1668-CD1.mp4",
        "VRKM-1668-CD2.mp4",
        "VRKM-1668-CD10.mp4",
    ]
    assert context.provider.calls == [
        ("/Downloads/4k2.com@vrkm01668_1_12000.mp4", "VRKM-1668-CD1.mp4"),
        ("/Downloads/4k2.com@vrkm01668_2_12000.mp4", "VRKM-1668-CD2.mp4"),
        ("/Downloads/4k2.com@vrkm01668_10_12000.mp4", "VRKM-1668-CD10.mp4"),
    ]
