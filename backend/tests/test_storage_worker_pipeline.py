from dataclasses import dataclass
from types import SimpleNamespace

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


def test_execute_current_magnet_attempt_marks_subtask_skipped_when_all_targets_exist(monkeypatch, tmp_path):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs
    from backend.app.modules.storage.worker.steps import execute_current_magnet_attempt

    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    target_folder = "/Movies/巨乳/MIDA-628"
    target_file = f"{target_folder}/MIDA-628.mp4"
    file_size = 6910439461

    class Result:
        success = True
        error_message = None
        result_paths = []

    class SearchFile:
        name = "MIDA-628.mp4"
        full_path = "/Search/MIDA-628.mp4"
        size = file_size
        is_directory = False
        is_search_result = True

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
            if path == target_folder:
                return [SearchFile()]
            return []

        def get_original_path(self, path):
            return target_file

        def list_files(self, path, force_refresh=False):
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

    def fake_execute_current_magnet_attempt(context, magnet):
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
    from backend.app.modules.storage.worker.steps import is_rename_name_exists_error

    error = RuntimeError(
        'api error Cloud 115open(342367138) api error: code: 20004, '
        'message: 很抱歉，该目录名称已存在。'
    )

    assert is_rename_name_exists_error(error) is True
    assert is_rename_name_exists_error(RuntimeError("permission denied")) is False


def test_rename_name_exists_reuses_existing_canonical_source_file() -> None:
    from types import SimpleNamespace

    from backend.app.modules.storage.worker.steps import rename_selected_videos

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
    from backend.app.modules.storage.worker.steps import move_renamed_videos

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

    def fake_execute_current_magnet_attempt(context, magnet):
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

    from backend.app.modules.storage.worker.steps import move_renamed_videos

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

    from backend.app.modules.storage.worker.steps import move_renamed_videos

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

    from backend.app.modules.storage.worker.steps import move_renamed_videos

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

    def fake_execute_current_magnet_attempt(context, magnet):
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


def test_poll_downloaded_video_files_searches_task_folder_before_download_root(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str]] = []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            if path == "/Downloads":
                return [RemoteFile("ACZD-165.mp4", "/Downloads/ACZD-165.mp4", 500 * 1024 * 1024)]
            return []

        def get_original_path(self, path):
            return ""

        def list_files(self, path, force_refresh=False):
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

    assert [file["path"] for file in files] == ["/Downloads/ACZD-165.mp4"]
    assert context.provider.search_calls == [
        ("ACZD-165", "/Downloads/storage_sub"),
        ("ACZD-165", "/Downloads/storage_sub"),
        ("ACZD-165", "/Downloads"),
    ]
    assert [log["context"]["search_scope"] for log in context.logs if log["message"] == "查找下载文件"] == [
        "task_download_folder",
        "task_download_folder",
        "download_root",
    ]


def test_poll_downloaded_video_files_does_not_search_root_when_task_folder_has_file(monkeypatch):
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import poll_downloaded_video_files

    monkeypatch.setattr("backend.app.modules.storage.worker.steps.time.sleep", lambda seconds: None)

    @dataclass
    class RemoteFile:
        name: str
        full_path: str
        size: int
        is_directory: bool = False
        is_search_result: bool = False

    class Provider:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, str]] = []

        def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
            self.search_calls.append((term, path))
            return [RemoteFile("ACZD-165.mp4", f"{path}/ACZD-165.mp4", 500 * 1024 * 1024)]

        def get_original_path(self, path):
            return ""

        def list_files(self, path, force_refresh=False):
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
    assert context.provider.search_calls == [("ACZD-165", "/Downloads/storage_sub")]


def test_subtask_pipeline_starts_next_magnet_only_after_current_failure(monkeypatch):
    import uuid
    from dataclasses import dataclass

    from backend.app.modules.storage.worker.steps import execute_subtask_pipeline

    attempt_order: list[str] = []

    def fake_execute_current_magnet_attempt(context, magnet):
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

    def fake_execute_current_magnet_attempt(context, magnet):
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
