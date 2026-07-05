# Storage Step Timeline Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the Jav Scrapling storage subtask step timeline in Media Forge, including per-step logs, result verification, cleanup, and realtime EventSource updates.

**Architecture:** Keep the current Media Forge Redis-backed main/subtask model and CloudDrive2 gateway. Add a small worker timeline layer around the existing storage worker so each magnet attempt runs through the original steps: prepare, submit_magnet, waiting_download, scan_files, select_videos, rename_files, move_files, verify_result, cleanup_files. Persist every step log to JSONL and publish the same entry through the existing realtime event bus.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Redis runtime state, CloudDrive2 gateway, JSONL task logs, Server-Sent Events, React 19, Ant Design Timeline, Vitest, Pytest.

---

## Source Mapping

Original Jav Scrapling files used as the source of behavior:

- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/state_machine.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/context.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/prepare.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/submit_magnet.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/wait_download.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/scan_files.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/select_videos.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/rename_files.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/move_files.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/verify_result.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/worker/steps/cleanup_files.py`
- `/Users/eastwood/Code/PycharmProjects/jav-scrapling/backend/app/modules/storage/domain/video_selector.py`

Current Media Forge files to modify:

- `backend/app/modules/storage/tasks/logs.py`: Store step metadata on each JSONL log entry.
- `backend/app/modules/storage/tasks/events.py`: Publish `storage.sub.log.appended` events.
- `backend/app/modules/storage/worker/timeline.py`: New shared step order, labels, and file classification helpers.
- `backend/app/modules/storage/worker/context.py`: Add owner-aware log and step helpers.
- `backend/app/modules/storage/worker/runner.py`: Create worker contexts with `owner_id`; publish subtask updates after failures and completion.
- `backend/app/modules/storage/worker/steps.py`: Replace coarse magnet handling with the original step-by-step pipeline.
- `frontend/src/api/storage/storageTasks/types.ts`: Add timeline fields to `StorageTaskLog`.
- `frontend/src/realtime/types.ts`: Add typed payload for `storage.sub.log.appended`.
- `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`: Render a step timeline and filter incoming log events by subtask.
- `frontend/src/pages/storage/tasks/StorageTasks.module.less`: Add compact timeline and log styles.
- `backend/tests/test_storage_realtime_events.py`: Extend JSONL and realtime log event coverage.
- `backend/tests/test_storage_worker_timeline.py`: New unit tests for step order, scan/select/rename/verify/cleanup behavior.
- `frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx`: New UI test for realtime timeline append.

## Task 1: Backend Log Entries and Realtime Log Events

**Files:**
- Modify: `backend/app/modules/storage/tasks/logs.py`
- Modify: `backend/app/modules/storage/tasks/events.py`
- Modify: `backend/tests/test_storage_realtime_events.py`

- [ ] **Step 1: Write failing backend log metadata tests**

Replace `backend/tests/test_storage_realtime_events.py` with:

```python
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.storage.tasks.events import publish_storage_sub_log_appended
from backend.app.modules.storage.tasks.logs import read_storage_subtask_logs, write_storage_subtask_log


def test_storage_subtask_log_round_trip_with_step_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))

    entry = write_storage_subtask_log(
        "sub-1",
        "INFO",
        "执行步骤: prepare",
        {"movie_id": "movie-1"},
        step="prepare",
        step_label="准备任务",
        event="step_started",
    )

    saved = read_storage_subtask_logs("sub-1")[0]
    assert entry == saved
    assert saved["message"] == "执行步骤: prepare"
    assert saved["context"] == {"movie_id": "movie-1"}
    assert saved["step"] == "prepare"
    assert saved["step_label"] == "准备任务"
    assert saved["event"] == "step_started"


def test_publish_storage_sub_log_appended_sends_entry_to_owner() -> None:
    owner_id = "user-storage-log"
    queue = event_bus.subscribe(owner_id)
    try:
        entry = {
            "timestamp": "2026-07-04T03:41:43.132033",
            "level": "INFO",
            "message": "执行步骤: cleanup_files",
            "context": {"download_path": "/云下载/storage_sub-1"},
            "step": "cleanup_files",
            "step_label": "清理临时文件",
            "event": "step_started",
        }

        publish_storage_sub_log_appended(owner_id, "sub-1", entry)

        event = queue.get_nowait()
        assert event.event == "storage.sub.log.appended"
        assert event.scope == "storage.sub"
        assert event.owner_id == owner_id
        assert event.resource_id == "sub-1"
        assert event.payload == entry
    finally:
        event_bus.unsubscribe(owner_id, queue)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_realtime_events.py -v
```

Expected: FAIL because `write_storage_subtask_log` does not accept `step`, `step_label`, or `event`, and `publish_storage_sub_log_appended` is missing.

- [ ] **Step 3: Implement log metadata fields**

Change `backend/app/modules/storage/tasks/logs.py` to:

```python
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path


def _log_path(subtask_id: str) -> Path:
    root = Path(os.getenv("APP_DATA_DIR", "data")) / "logs/storage/tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{subtask_id}.jsonl"


def write_storage_subtask_log(
    subtask_id: str,
    level: str,
    message: str,
    context: dict | None = None,
    *,
    step: str | None = None,
    step_label: str | None = None,
    event: str | None = None,
) -> dict:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "context": context or {},
    }
    if step:
        entry["step"] = step
    if step_label:
        entry["step_label"] = step_label
    if event:
        entry["event"] = event
    with _log_path(subtask_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_storage_subtask_logs(subtask_id: str) -> list[dict]:
    path = _log_path(subtask_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 4: Implement realtime log publishing**

Add this function to `backend/app/modules/storage/tasks/events.py`:

```python
def publish_storage_sub_log_appended(owner_id: str, subtask_id: str, entry: dict) -> None:
    event_bus.publish(make_realtime_event(
        event="storage.sub.log.appended",
        scope="storage.sub",
        owner_id=owner_id,
        resource_id=subtask_id,
        payload=entry,
    ))
```

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/storage/tasks/logs.py backend/app/modules/storage/tasks/events.py backend/tests/test_storage_realtime_events.py
git commit -m "feat: publish storage subtask timeline logs"
```

## Task 2: Worker Timeline Context

**Files:**
- Create: `backend/app/modules/storage/worker/timeline.py`
- Modify: `backend/app/modules/storage/worker/context.py`
- Modify: `backend/app/modules/storage/worker/runner.py`
- Test: `backend/tests/test_storage_worker_timeline.py`

- [ ] **Step 1: Write failing timeline metadata tests**

Create `backend/tests/test_storage_worker_timeline.py` with:

```python
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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_timeline.py -v
```

Expected: FAIL because `backend.app.modules.storage.worker.timeline` does not exist.

- [ ] **Step 3: Add timeline constants and file classification**

Create `backend/app/modules/storage/worker/timeline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

PIPELINE_STEPS = [
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

STEP_LABELS = {
    "prepare": "准备任务",
    "submit_magnet": "提交磁力",
    "waiting_download": "云端下载",
    "scan_files": "扫描文件",
    "select_videos": "识别主视频",
    "rename_files": "重命名",
    "move_files": "移动文件",
    "verify_result": "校验结果",
    "cleanup_files": "清理临时文件",
    "done": "完成",
}

SUBTITLE_EXTENSIONS = frozenset({".srt", ".ass", ".ssa", ".sub", ".sup", ".idx"})
COVER_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp"})


@dataclass
class ClassifiedFiles:
    selected_videos: list[dict] = field(default_factory=list)
    excluded_files: list[dict] = field(default_factory=list)
    subtitle_files: list[dict] = field(default_factory=list)
    cover_files: list[dict] = field(default_factory=list)
    other_files: list[dict] = field(default_factory=list)


def classify_scanned_files(scanned: list[dict], config: dict) -> ClassifiedFiles:
    result = ClassifiedFiles()
    video_exts = {str(ext).lower() for ext in config.get("video_extensions", [])}
    min_size = int(config.get("minimum_video_size_mb", 100)) * 1024 * 1024
    excluded_keywords = [str(item).lower() for item in config.get("excluded_filename_keywords", [])]

    for file_info in scanned:
        name = str(file_info["name"])
        ext = PurePosixPath(name).suffix.lower()
        lower_name = name.lower()
        size = int(file_info.get("size") or 0)
        if any(keyword in lower_name for keyword in excluded_keywords):
            result.excluded_files.append(file_info)
        elif ext in video_exts and size >= min_size:
            result.selected_videos.append({**file_info, "video_type": "main"})
        elif ext in video_exts:
            result.excluded_files.append(file_info)
        elif ext in SUBTITLE_EXTENSIONS:
            result.subtitle_files.append(file_info)
        elif ext in COVER_EXTENSIONS:
            result.cover_files.append(file_info)
        else:
            result.other_files.append(file_info)

    return result
```

- [ ] **Step 4: Add owner-aware logging and step publishing to context**

Replace `backend/app/modules/storage/worker/context.py` with:

```python
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.tasks.events import publish_storage_sub_log_appended, publish_storage_sub_updated
from backend.app.modules.storage.tasks.logs import write_storage_subtask_log
from backend.app.modules.storage.worker.timeline import STEP_LABELS


@dataclass
class StorageWorkerContext:
    db: Session
    main_task: StorageMainTask
    subtask: StorageSubTask
    config: dict
    provider: object
    owner_id: str

    def set_step(self, step: str) -> None:
        self.subtask.step = step
        self.db.flush()
        publish_storage_sub_updated(self.owner_id, self.subtask)
        self.log(
            "INFO",
            f"执行步骤: {step}",
            {"step": step},
            step=step,
            event="step_started",
        )

    def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
        *,
        step: str | None = None,
        event: str | None = None,
    ) -> dict:
        current_step = step or self.subtask.step
        entry = write_storage_subtask_log(
            str(self.subtask.id),
            level,
            message,
            context or {},
            step=current_step,
            step_label=STEP_LABELS.get(current_step),
            event=event,
        )
        publish_storage_sub_log_appended(self.owner_id, str(self.subtask.id), entry)
        return entry

    def publish_subtask(self) -> None:
        self.db.flush()
        publish_storage_sub_updated(self.owner_id, self.subtask)
```

- [ ] **Step 5: Pass owner ID and publish subtask state from runner**

In `backend/app/modules/storage/worker/runner.py`, change context creation to include `owner_id`:

```python
context = StorageWorkerContext(
    db=db,
    main_task=main_task,
    subtask=subtask,
    config=config,
    provider=provider,
    owner_id=str(main_task.created_by),
)
```

Replace the direct `write_storage_subtask_log` calls inside the successful `try` block with:

```python
execute_subtask_pipeline(context)
context.log(
    "INFO",
    "存储子任务执行结束",
    {
        "main_task_id": str(main_task.id),
        "status": subtask.status,
        "step": subtask.step,
    },
    step=subtask.step,
    event="subtask_finished",
)
context.publish_subtask()
```

Replace the direct failure log inside the `except Exception as exc` block with:

```python
context.log(
    "ERROR",
    f"存储子任务执行失败: {exc}",
    {
        "main_task_id": str(main_task.id),
        "step": subtask.step,
    },
    step=subtask.step,
    event="subtask_failed",
)
context.publish_subtask()
```

- [ ] **Step 6: Run timeline tests and storage realtime tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/storage/worker/timeline.py backend/app/modules/storage/worker/context.py backend/app/modules/storage/worker/runner.py backend/tests/test_storage_worker_timeline.py
git commit -m "feat: add storage worker timeline context"
```

## Task 3: Step-by-Step Magnet Attempt Pipeline

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_timeline.py`

- [ ] **Step 1: Add failing unit tests for verification and cleanup**

Append this fake provider and tests to `backend/tests/test_storage_worker_timeline.py`:

```python
from types import SimpleNamespace

from backend.app.modules.storage.worker.steps import verify_moved_files, cleanup_download_folder


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
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_timeline.py -v
```

Expected: FAIL because `verify_moved_files` and `cleanup_download_folder` are missing.

- [ ] **Step 3: Add verification and cleanup helpers**

Add these functions to `backend/app/modules/storage/worker/steps.py`:

```python
def verify_moved_files(context, moved_files: list[dict]) -> bool:
    all_ok = True
    for video in moved_files:
        paths_to_verify = []
        moved_path = video.get("moved_path") or video.get("target")
        if moved_path:
            paths_to_verify.append(("moved", moved_path))
        for copied_path in video.get("copied_paths", []):
            paths_to_verify.append(("copied", copied_path))

        if not paths_to_verify:
            all_ok = False
            context.log("ERROR", f"验证失败: {video.get('name')} 无任何目标路径", step="verify_result")
            continue

        expected_size = int(video.get("size") or 0)
        for label, path in paths_to_verify:
            info = context.provider.find_file(path)
            if not info:
                all_ok = False
                context.log("ERROR", f"验证失败: {label} 文件不存在 {path}", step="verify_result")
                continue
            actual_size = int(getattr(info, "size", 0) or 0)
            if expected_size > 0 and abs(actual_size - expected_size) > 1024:
                all_ok = False
                context.log(
                    "ERROR",
                    f"验证失败: {label} 大小不匹配 {PurePosixPath(path).name} (expected={expected_size}, actual={actual_size})",
                    step="verify_result",
                )

    if all_ok:
        context.log("INFO", "验证通过: 所有文件完整 (含复制目标)", step="verify_result")
    return all_ok


def cleanup_download_folder(context, download_folder: str, config: dict) -> None:
    if download_folder and config.get("use_task_subfolder", True):
        try:
            context.provider.delete_file(download_folder)
            context.log("INFO", f"已清理下载目录: {download_folder}", step="cleanup_files")
        except Exception as exc:
            context.log("WARNING", f"清理下载目录失败 (非致命): {exc}", step="cleanup_files")
    context.log("INFO", "清理完成", step="cleanup_files")
```

- [ ] **Step 4: Replace the coarse attempt body with original step execution**

In `backend/app/modules/storage/worker/steps.py`, replace `execute_current_magnet_attempt` with this structure:

```python
def execute_current_magnet_attempt(context, magnet: dict) -> bool:
    from backend.app.modules.storage.tasks.policies import build_video_filename, code_folder_from_filename

    subtask = context.subtask
    config = context.config
    provider = context.provider
    magnet_url = magnet.get("magnet_url", "")
    if not magnet_url:
        context.log("WARNING", "磁力缺少链接", {"magnet_id": magnet.get("id")}, step="prepare")
        return False

    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"
    subtask.download_path = download_folder

    context.set_step("prepare")
    tags = list(magnet.get("tags") or [])
    preview_name = build_video_filename(subtask.movie_code, f"{subtask.movie_code}.mp4", tags, 0, 1)
    code_folder = code_folder_from_filename(preview_name)
    target_root = config.get("target_folder", "/Movies")
    target_locations = list(subtask.target_locations or [])
    target_paths = [f"{target_root}/{location}/{code_folder}" for location in target_locations] or [f"{target_root}/{code_folder}"]
    subtask.target_paths = target_paths
    context.log(
        "INFO",
        f"准备完成: download={download_folder}, target={target_paths[-1]}, targets={target_paths}, suffix={preview_name.replace(subtask.movie_code.upper(), '').rsplit('.', 1)[0]}",
        {"download_path": download_folder, "target_paths": target_paths, "magnet_id": magnet.get("id")},
        step="prepare",
    )

    context.set_step("submit_magnet")
    try:
        context.log(
            "INFO",
            "准备提交磁力到 CloudDrive2",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder},
            step="submit_magnet",
        )
        ensure_directory_chain(provider, download_folder)
        result = provider.submit_offline_download(magnet_url, download_folder)
        context.log(
            "INFO",
            "磁力链接已提交",
            {"magnet_id": magnet.get("id"), "download_folder": download_folder, "result_paths": getattr(result, "result_paths", [])},
            step="submit_magnet",
        )
    except Exception as exc:
        message = str(exc)
        if "10008" not in message and "任务已存在" not in message:
            context.log("ERROR", f"提交磁力失败: {exc}", {"magnet_id": magnet.get("id")}, step="submit_magnet")
            return False
        context.log("WARNING", "磁力链接已存在 (code 10008)，搜索现有下载中", {"magnet_id": magnet.get("id")}, step="submit_magnet")

    context.set_step("waiting_download")
    search_terms = [subtask.movie_code]
    search_paths = [download_folder, download_root, *target_paths]
    found_files = poll_downloaded_video_files(context, search_terms, search_paths)
    if not found_files:
        context.log("WARNING", "未在下载目录找到可用视频文件", {"magnet_id": magnet.get("id"), "search_paths": search_paths}, step="waiting_download")
        return False

    total_size = sum(int(file.get("size") or 0) for file in found_files)
    context.log(
        "INFO",
        f"下载完成: 检测到 {len(found_files)} 个文件, 总大小 {total_size / (1024 * 1024):.1f} MB",
        {"file_count": len(found_files), "total_size": total_size},
        step="waiting_download",
    )

    context.set_step("scan_files")
    scanned = scan_found_files(found_files)
    context.log("INFO", f"扫描到 {len(scanned)} 个文件", {"file_count": len(scanned)}, step="scan_files")

    context.set_step("select_videos")
    classified = classify_scanned_files(scanned, config)
    context.log(
        "INFO",
        f"文件筛选: videos={len(classified.selected_videos)}, excluded={len(classified.excluded_files)}, subtitles={len(classified.subtitle_files)}, covers={len(classified.cover_files)}, other={len(classified.other_files)}",
        step="select_videos",
    )
    if not classified.selected_videos:
        context.log("WARNING", "扫描到文件但未识别到主视频", {"magnet_id": magnet.get("id"), "file_count": len(scanned)}, step="select_videos")
        return False

    context.set_step("rename_files")
    renamed_files = rename_selected_videos(context, classified.selected_videos, tags)

    context.set_step("move_files")
    moved_files, skipped_files = move_renamed_videos(context, renamed_files, target_paths)
    subtask.renamed_files = renamed_files
    subtask.moved_files = moved_files
    subtask.skipped_files = skipped_files
    context.publish_subtask()
    if not moved_files:
        context.log("WARNING", "没有文件完成移动或复制", {"skipped_files": skipped_files}, step="move_files")
        return False

    context.set_step("verify_result")
    if not verify_moved_files(context, moved_files):
        return False

    context.set_step("cleanup_files")
    cleanup_download_folder(context, download_folder, config)

    subtask.result = {"status": "success", "files": moved_files}
    context.log("INFO", "磁力任务处理成功", {"magnet_id": magnet.get("id"), "files": moved_files}, step="cleanup_files", event="magnet_success")
    return True
```

- [ ] **Step 5: Add helper imports and helper functions used by the new pipeline**

Add this import near the top of `backend/app/modules/storage/worker/steps.py`:

```python
from backend.app.modules.storage.worker.timeline import classify_scanned_files
```

Add these helper functions below `target_files_exist`:

```python
def scan_found_files(found_files: list[dict]) -> list[dict]:
    return [
        {
            "name": file["name"],
            "path": file["path"],
            "size": int(file.get("size") or 0),
            "is_dir": bool(file.get("is_dir", False)),
        }
        for file in found_files
        if not file.get("is_dir", False)
    ]


def rename_selected_videos(context, selected_videos: list[dict], tags: list[str]) -> list[dict]:
    from backend.app.modules.storage.tasks.policies import build_video_filename

    renamed = []
    total = len(selected_videos)
    for index, video in enumerate(selected_videos):
        old_path = video["path"]
        new_name = build_video_filename(context.subtask.movie_code, video["name"], tags, index, total)
        new_path = str(PurePosixPath(old_path).parent / new_name)
        if PurePosixPath(old_path).name == new_name:
            renamed.append({**video, "renamed_path": old_path, "renamed_name": new_name})
            context.log("INFO", f"重命名: {video['name']} → {new_name}", step="rename_files")
            continue
        try:
            context.provider.rename_file(old_path, new_name)
            renamed.append({**video, "renamed_path": new_path, "renamed_name": new_name})
            context.log("INFO", f"重命名: {video['name']} → {new_name}", step="rename_files")
        except Exception as exc:
            context.log("ERROR", f"重命名失败: {video['name']}: {exc}", step="rename_files")
            renamed.append({**video, "rename_error": str(exc)})
    return renamed


def _target_file_exists(provider, target_path: str) -> bool:
    try:
        found = provider.find_file(target_path)
        return bool(found and int(getattr(found, "size", 0) or 0) > 0)
    except Exception:
        return False


def move_renamed_videos(context, renamed_files: list[dict], target_paths: list[str]) -> tuple[list[dict], list[dict]]:
    moved: list[dict] = []
    skipped: list[dict] = []
    copy_targets = target_paths[:-1] if len(target_paths) > 1 else []
    move_target = target_paths[-1]

    if context.config.get("auto_create_target_folder", True):
        for target_path in target_paths:
            ensure_directory_chain(context.provider, target_path)
            context.log("INFO", f"已创建文件夹: {target_path}", step="move_files")

    for file_info in renamed_files:
        if file_info.get("rename_error"):
            skipped.append({**file_info, "skip_reason": "rename_failed"})
            context.log("WARNING", f"跳过重命名失败的文件: {file_info['name']}", step="move_files")
            continue

        src = file_info.get("renamed_path") or file_info["path"]
        file_name = PurePosixPath(src).name
        existing_targets = [str(PurePosixPath(target) / file_name) for target in target_paths if _target_file_exists(context.provider, str(PurePosixPath(target) / file_name))]
        if len(existing_targets) == len(target_paths):
            skipped.append({**file_info, "skip_reason": "target_exists", "existing_targets": existing_targets})
            context.log("INFO", f"跳过已存在: {file_name}", {"existing_targets": existing_targets}, step="move_files")
            continue

        copied_paths = []
        for copy_target in copy_targets:
            copy_dst = str(PurePosixPath(copy_target) / file_name)
            if _target_file_exists(context.provider, copy_dst):
                copied_paths.append(copy_dst)
                context.log("INFO", f"跳过已存在: {file_name}", {"target": copy_dst}, step="move_files")
                continue
            context.provider.copy_file(src, copy_target)
            copied_paths.append(copy_dst)
            context.log("INFO", f"已复制: {file_name} → {copy_target}", step="move_files")

        move_dst = str(PurePosixPath(move_target) / file_name)
        if _target_file_exists(context.provider, move_dst):
            moved.append({**file_info, "moved_path": move_dst, "copied_paths": copied_paths})
            context.log("INFO", f"跳过已存在: {file_name}", {"target": move_dst}, step="move_files")
            continue
        context.provider.move_files([src], move_target)
        moved.append({**file_info, "moved_path": move_dst, "copied_paths": copied_paths})
        context.log("INFO", f"已移动: {file_name} → {move_target}", step="move_files")

    return moved, skipped
```

- [ ] **Step 6: Update polling logs to original wording**

Inside `poll_downloaded_video_files`, replace the “未发现/发现可用视频文件” log messages with:

```python
context.log(
    "INFO",
    f"轮询 #{poll_index}: 目录为空，等待中",
    {"poll_index": poll_index, "max_poll_count": max_poll_count, "search_paths": search_paths},
    step="waiting_download",
)
```

When files are found, return them without logging “下载完成”; the new `execute_current_magnet_attempt` writes “下载完成: 检测到 …”.

When polling reaches the maximum, log:

```python
context.log(
    "WARNING",
    f"轮询次数超过上限: {max_poll_count}/{max_poll_count}，跳过当前磁力",
    {"max_poll_count": max_poll_count, "search_paths": search_paths},
    step="waiting_download",
)
```

- [ ] **Step 7: Make subtask status use the original final step**

In `execute_subtask_pipeline`, change `subtask.step = "cloud_download"` to:

```python
subtask.step = "prepare"
context.publish_subtask()
```

After a successful magnet attempt, keep:

```python
subtask.status = "completed"
subtask.step = "done"
subtask.finished_at = datetime.now(timezone.utc)
context.publish_subtask()
return
```

When all magnets fail, add:

```python
context.publish_subtask()
```

- [ ] **Step 8: Run backend timeline tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_timeline.py
git commit -m "feat: run storage subtasks through timeline steps"
```

## Task 4: Frontend Step Timeline over EventSource

**Files:**
- Modify: `frontend/src/api/storage/storageTasks/types.ts`
- Modify: `frontend/src/realtime/types.ts`
- Modify: `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTasks.module.less`
- Create: `frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx`

- [ ] **Step 1: Write failing UI test for realtime log append and filtering**

Create `frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StorageSubTaskDetailPage from '../StorageSubTaskDetailPage'

const subscribeRealtime = vi.fn()

vi.mock('@/api/storage/storageTasks', () => ({
  getStorageSubTask: vi.fn().mockResolvedValue({
    id: 'sub-1',
    main_task_id: 'main-1',
    movie_id: 'movie-1',
    movie_code: 'ABC-001',
    movie_title: 'Movie',
    status: 'running',
    step: 'prepare',
    storage_mode: 'single',
    selected_storage_location: '巨乳',
    target_locations: ['巨乳'],
    download_path: '/云下载/storage_sub-1',
    target_paths: [],
    magnet_attempts: [],
    current_magnet_id: null,
    current_magnet_url: '',
    renamed_files: [],
    moved_files: [],
    skipped_files: [],
    result: {},
  }),
  getStorageSubTaskLogs: vi.fn().mockResolvedValue([
    {
      timestamp: '2026-07-04T03:41:43.132033',
      level: 'INFO',
      message: '执行步骤: prepare',
      context: {},
      step: 'prepare',
      step_label: '准备任务',
      event: 'step_started',
    },
  ]),
}))

vi.mock('@/realtime/eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  subscribeRealtime: (eventName: string, handler: unknown) => {
    subscribeRealtime(eventName, handler)
    return () => {}
  },
}))

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ id: 'sub-1' }),
}))

describe('StorageSubTaskDetailPage timeline', () => {
  beforeEach(() => {
    subscribeRealtime.mockClear()
  })

  it('renders step timeline and appends only logs for the current subtask', async () => {
    render(<StorageSubTaskDetailPage />)

    expect(await screen.findByText('步骤时间线')).toBeInTheDocument()
    expect(screen.getByText('准备任务')).toBeInTheDocument()

    const logHandler = subscribeRealtime.mock.calls.find((call) => call[0] === 'storage.sub.log.appended')?.[1]
    expect(logHandler).toBeTypeOf('function')

    logHandler({
      resource_id: 'other-sub',
      payload: {
        timestamp: '2026-07-04T03:41:44.000000',
        level: 'INFO',
        message: '不应该显示',
        context: {},
        step: 'submit_magnet',
        step_label: '提交磁力',
      },
    })
    logHandler({
      resource_id: 'sub-1',
      payload: {
        timestamp: '2026-07-04T03:41:45.000000',
        level: 'INFO',
        message: '磁力链接已提交',
        context: {},
        step: 'submit_magnet',
        step_label: '提交磁力',
      },
    })

    await waitFor(() => {
      expect(screen.queryByText('不应该显示')).not.toBeInTheDocument()
      expect(screen.getByText('磁力链接已提交')).toBeInTheDocument()
    })
  })
})
```

- [ ] **Step 2: Run UI test and verify failure**

Run:

```bash
cd frontend
npm test -- src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx
```

Expected: FAIL because the page does not render “步骤时间线” and the log subscriber does not filter by `resource_id`.

- [ ] **Step 3: Add log metadata types**

In `frontend/src/api/storage/storageTasks/types.ts`, replace `StorageTaskLog` with:

```ts
export interface StorageTaskLog {
  timestamp: string
  level: string
  message: string
  context: Record<string, unknown>
  step?: string
  step_label?: string
  event?: string
}
```

In `frontend/src/realtime/types.ts`, add:

```ts
import type { StorageMainTask, StorageTaskLog } from '@/api/storage/storageTasks/types'
```

Replace the existing storage import line with the combined import above, then add:

```ts
export type StorageSubLogAppendedPayload = StorageTaskLog
```

- [ ] **Step 4: Add step timeline constants and grouping to the detail page**

In `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`, add these constants below `levelColors`:

```tsx
const stepOrder = [
  'prepare',
  'submit_magnet',
  'waiting_download',
  'scan_files',
  'select_videos',
  'rename_files',
  'move_files',
  'verify_result',
  'cleanup_files',
]

const stepLabels: Record<string, string> = {
  prepare: '准备任务',
  submit_magnet: '提交磁力',
  waiting_download: '云端下载',
  scan_files: '扫描文件',
  select_videos: '识别主视频',
  rename_files: '重命名',
  move_files: '移动文件',
  verify_result: '校验结果',
  cleanup_files: '清理临时文件',
}

function logsForStep(logs: StorageTaskLog[], step: string) {
  return logs.filter((log) => log.step === step || log.context?.step === step)
}

function stepColor(subtask: StorageSubTask, logs: StorageTaskLog[], step: string) {
  if (logs.some((log) => log.level === 'ERROR')) return 'red'
  if (logs.length > 0) return 'green'
  if (subtask.step === step) return 'blue'
  return 'gray'
}
```

- [ ] **Step 5: Filter log append events by subtask**

In `StorageSubTaskDetailPage.tsx`, replace the `storage.sub.log.appended` handler with:

```tsx
const unsubscribeLog = subscribeRealtime<StorageTaskLog>(
  'storage.sub.log.appended',
  (event: RealtimeEvent<StorageTaskLog>) => {
    if (event.resource_id !== id) return
    setLogs((current) => current.concat(event.payload))
  },
)
```

- [ ] **Step 6: Render the step timeline before the raw log card**

Add this card before `<Card title="任务日志">`:

```tsx
<Card title="步骤时间线" style={{ marginBottom: 16 }}>
  <Timeline
    items={stepOrder.map((step) => {
      const stepLogs = logsForStep(logs, step)
      const lastLog = stepLogs.at(-1)
      return {
        color: stepColor(subtask, stepLogs, step),
        children: (
          <div className={styles.stepTimelineItem}>
            <div className={styles.stepTimelineHeader}>
              <Typography.Text strong>{stepLabels[step]}</Typography.Text>
              <Typography.Text type="secondary">{step}</Typography.Text>
            </div>
            {lastLog ? (
              <Typography.Text
                type={lastLog.level === 'ERROR' ? 'danger' : 'secondary'}
                className={styles.stepTimelineMessage}
              >
                {formatTime(lastLog.timestamp)} {lastLog.message}
              </Typography.Text>
            ) : (
              <Typography.Text type="secondary" className={styles.stepTimelineMessage}>
                等待执行
              </Typography.Text>
            )}
          </div>
        ),
      }
    })}
  />
</Card>
```

- [ ] **Step 7: Add timeline styles**

Append to `frontend/src/pages/storage/tasks/StorageTasks.module.less`:

```less
.stepTimelineItem {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stepTimelineHeader {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.stepTimelineMessage {
  display: block;
  word-break: break-word;
}
```

- [ ] **Step 8: Run frontend timeline test**

Run:

```bash
cd frontend
npm test -- src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/storage/storageTasks/types.ts frontend/src/realtime/types.ts frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx frontend/src/pages/storage/tasks/StorageTasks.module.less frontend/src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx
git commit -m "feat: show storage subtask step timeline"
```

## Task 5: End-to-End Verification

**Files:**
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/app/modules/storage/worker/context.py`
- Verify: `frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx`

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_realtime_events.py backend/tests/test_storage_worker_timeline.py -v
```

Expected: PASS.

- [ ] **Step 2: Run targeted frontend tests**

Run:

```bash
cd frontend
npm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx src/pages/storage/tasks/__tests__/storage-subtask-detail-timeline.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend type and production build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with Vite production build output.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/steps.py backend/app/modules/storage/worker/context.py frontend/src/pages/storage/tasks/StorageSubTaskDetailPage.tsx
```

Expected: diff contains only storage timeline, logging, verification, cleanup, and UI changes.

- [ ] **Step 5: Commit verification fixes if any files changed after Task 4**

```bash
git add backend frontend
git commit -m "test: verify storage timeline flow"
```

If Step 4 shows no file changes after test runs, skip this commit.

## Self-Review

- Spec coverage: The plan ports the original step order, adds per-step logs, restores verify_result and cleanup_files, and sends step/log updates through the existing EventSource pipeline.
- Current-project fit: The plan keeps current Redis main task scheduling, storage task tables, file finder search support, CloudDrive2 gateway calls, and magnet weight ordering.
- Risk control: Backend tests cover log metadata, SSE log publishing, step order, file classification, verification, and cleanup. Frontend tests cover timeline rendering and per-subtask realtime filtering.
