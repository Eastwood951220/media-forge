from types import SimpleNamespace

from backend.app.modules.storage.worker.steps import verify_moved_files, cleanup_download_folder
from backend.app.modules.storage.worker.timeline import PIPELINE_STEPS, STEP_LABELS, classify_scanned_files


def test_pipeline_steps_match_original_storage_flow() -> None:
    assert PIPELINE_STEPS == [
        "prepare",
        "submit_magnet",
        "waiting_download",
        "scan_files",
        "select_videos",
        "rename_files",
        "move_files",
        "verify_result",
        "cleanup_files",
    ]
    assert STEP_LABELS["prepare"] == "准备任务"
    assert STEP_LABELS["submit_magnet"] == "提交磁力"
    assert STEP_LABELS["waiting_download"] == "云端下载"
    assert STEP_LABELS["scan_files"] == "扫描文件"
    assert STEP_LABELS["select_videos"] == "识别主视频"
    assert STEP_LABELS["rename_files"] == "重命名"
    assert STEP_LABELS["move_files"] == "移动文件"
    assert STEP_LABELS["verify_result"] == "校验结果"
    assert STEP_LABELS["cleanup_files"] == "清理临时文件"


def test_classify_scanned_files_counts_original_categories() -> None:
    scanned = [
        {"name": "ABC-001.mp4", "path": "/d/ABC-001.mp4", "size": 200 * 1024 * 1024},
        {"name": "sample.mp4", "path": "/d/sample.mp4", "size": 5 * 1024 * 1024},
        {"name": "ABC-001.srt", "path": "/d/ABC-001.srt", "size": 1000},
        {"name": "cover.jpg", "path": "/d/cover.jpg", "size": 1000},
        {"name": "readme.txt", "path": "/d/readme.txt", "size": 1000},
    ]
    result = classify_scanned_files(
        scanned,
        {
            "video_extensions": [".mp4", ".mkv"],
            "minimum_video_size_mb": 100,
            "excluded_filename_keywords": ["sample"],
        },
    )

    assert [item["name"] for item in result.selected_videos] == ["ABC-001.mp4"]
    assert [item["name"] for item in result.excluded_files] == ["sample.mp4"]
    assert [item["name"] for item in result.subtitle_files] == ["ABC-001.srt"]
    assert [item["name"] for item in result.cover_files] == ["cover.jpg"]
    assert [item["name"] for item in result.other_files] == ["readme.txt"]


class FakeProvider:
    def __init__(self) -> None:
        self.files = {
            "/target/ABC-001/ABC-001-C.mp4": SimpleNamespace(size=200 * 1024 * 1024),
            "/copy/ABC-001/ABC-001-C.mp4": SimpleNamespace(size=200 * 1024 * 1024),
        }
        self.deleted: list[str] = []

    def find_file(self, path: str):
        return self.files.get(path)

    def delete_file(self, path: str):
        self.deleted.append(path)
        return SimpleNamespace(success=True)


class FakeContext:
    def __init__(self) -> None:
        self.provider = FakeProvider()
        self.messages: list[str] = []

    def log(self, level: str, message: str, context: dict | None = None, *, step: str | None = None, event: str | None = None):
        self.messages.append(message)
        return {"level": level, "message": message, "context": context or {}, "step": step, "event": event}


def test_verify_moved_files_checks_moved_and_copied_paths() -> None:
    context = FakeContext()
    moved = [
        {
            "name": "ABC-001-C.mp4",
            "size": 200 * 1024 * 1024,
            "moved_path": "/target/ABC-001/ABC-001-C.mp4",
            "copied_paths": ["/copy/ABC-001/ABC-001-C.mp4"],
        }
    ]

    assert verify_moved_files(context, moved) is True
    assert "验证通过: 所有文件完整 (含复制目标)" in context.messages


def test_cleanup_download_folder_deletes_task_folder_when_enabled() -> None:
    context = FakeContext()

    cleanup_download_folder(context, "/云下载/storage_sub-1", {"use_task_subfolder": True})

    assert context.provider.deleted == ["/云下载/storage_sub-1"]
    assert "清理完成" in context.messages
