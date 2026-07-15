# Storage VR Target And Quality Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store VR movies under `VR/<code_folder>` within each resolved target category and drop smaller duplicate quality variants from a magnet before rename and move.

**Architecture:** Keep the storage worker pipeline intact. Add pure policy helpers in `backend/app/modules/storage/tasks/policies.py`, pass `Movie.tags` separately from magnet tags into target planning, and run quality-variant filtering after main-video classification but before rename.

**Tech Stack:** Python 3.12+, FastAPI backend, SQLAlchemy models, pytest tests in `backend/tests/test_storage_worker_pipeline.py`.

## Global Constraints

- VR detection uses only `Movie.tags`.
- `MovieMagnet.tags` must not be used for VR detection.
- Magnet tags continue to drive existing filename suffix behavior such as `-C`, `-U`, and `-UC`.
- Quality duplicate filtering runs after main-video selection and before rename.
- True multi-part markers such as `CD1/CD2`, `part1/part2`, and `disc1/disc2` must not be merged.
- No frontend UI changes.
- No database schema changes.
- No CloudDrive2 provider API changes.
- Do not reorganize files already stored before this change.
- Preserve existing magnet ordering and selected magnet logic.

---

## File Structure

- Modify `backend/app/modules/storage/tasks/policies.py`: add pure helpers for VR tag detection, VR path insertion, quality-key normalization, and quality-variant dedupe.
- Modify `backend/app/modules/storage/worker/target_planning.py`: accept `movie_tags`, use them for VR target paths, and keep magnet tags for filename suffix preview.
- Modify `backend/app/modules/storage/worker/steps.py`: pass `movie.tags` into the current magnet attempt and target planning.
- Modify `backend/app/modules/storage/worker/file_pipeline.py`: run dedupe after `classify_scanned_files` and log dropped variants only when needed.
- Modify `backend/tests/test_storage_worker_pipeline.py`: add focused unit tests for policy helpers and integration tests for target planning and pipeline behavior.

---

### Task 1: Storage Policy Helpers

**Files:**
- Modify: `backend/app/modules/storage/tasks/policies.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Consumes: existing `build_video_filename(movie_code: str, original_name: str, tags: list[str], index: int, total: int) -> str`
- Produces:
  - `is_vr_movie_tags(tags: list[str]) -> bool`
  - `insert_vr_directory(target_path: str, code_folder: str) -> str`
  - `quality_dedupe_key(filename: str) -> str`
  - `dedupe_quality_variants(videos: list[dict]) -> tuple[list[dict], list[dict]]`

- [ ] **Step 1: Write failing tests for VR tag detection and target path insertion**

Append these tests to `backend/tests/test_storage_worker_pipeline.py` near the existing storage policy tests:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_is_vr_movie_tags_matches_only_clear_vr_tags backend/tests/test_storage_worker_pipeline.py::test_insert_vr_directory_before_code_folder_without_duplication -v
```

Expected: FAIL with import errors for `is_vr_movie_tags` and `insert_vr_directory`.

- [ ] **Step 3: Implement VR helper functions**

In `backend/app/modules/storage/tasks/policies.py`, add these imports and functions while keeping existing functions unchanged:

```python
from pathlib import PurePosixPath


VR_TAG_PATTERN = re.compile(r"(^|[^a-z0-9])vr([^a-z0-9]|$)", re.IGNORECASE)


def is_vr_movie_tags(tags: list[str]) -> bool:
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip()
        if not normalized:
            continue
        if normalized.lower() == "vr":
            return True
        if normalized.upper().startswith("VR") and len(normalized) > 2:
            return True
        if VR_TAG_PATTERN.search(normalized):
            return True
    return False


def insert_vr_directory(target_path: str, code_folder: str) -> str:
    path = PurePosixPath(target_path)
    if path.name != code_folder:
        return str(path / "VR" / code_folder)
    parent = path.parent
    if parent.name.upper() == "VR":
        return str(path)
    return str(parent / "VR" / path.name)
```

If `PurePosixPath` is already imported in the file, reuse the existing import instead of duplicating it.

- [ ] **Step 4: Run VR helper tests to verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_is_vr_movie_tags_matches_only_clear_vr_tags backend/tests/test_storage_worker_pipeline.py::test_insert_vr_directory_before_code_folder_without_duplication -v
```

Expected: PASS.

- [ ] **Step 5: Write failing tests for quality dedupe helpers**

Append these tests to `backend/tests/test_storage_worker_pipeline.py`:

```python
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
```

- [ ] **Step 6: Run quality helper tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_quality_dedupe_key_removes_quality_tokens_but_preserves_parts backend/tests/test_storage_worker_pipeline.py::test_dedupe_quality_variants_keeps_largest_per_group -v
```

Expected: FAIL with import errors for `quality_dedupe_key` and `dedupe_quality_variants`.

- [ ] **Step 7: Implement quality dedupe helper functions**

In `backend/app/modules/storage/tasks/policies.py`, add:

```python
QUALITY_TOKEN_PATTERN = re.compile(
    r"(?i)(^|[\s._\-\[\]()])(?:8k|4k|2k|uhd|fhd|hd|2160p|1440p|1080p|720p)(?=$|[\s._\-\[\]()])"
)
SEPARATOR_PATTERN = re.compile(r"[\s._\-\[\]()]+" )


def quality_dedupe_key(filename: str) -> str:
    stem = PurePosixPath(str(filename or "")).stem.lower()
    without_quality = QUALITY_TOKEN_PATTERN.sub(" ", stem)
    normalized = SEPARATOR_PATTERN.sub("_", without_quality).strip("_")
    return normalized or stem


def _video_sort_key(video: dict) -> tuple[int, str, str]:
    return (
        -int(video.get("size") or 0),
        str(video.get("name") or "").lower(),
        str(video.get("path") or "").lower(),
    )


def dedupe_quality_variants(videos: list[dict]) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    for video in videos:
        key = quality_dedupe_key(str(video.get("name") or ""))
        if not key:
            key = str(video.get("path") or id(video))
        groups.setdefault(key, []).append(video)

    kept_by_identity: set[int] = set()
    dropped: list[dict] = []
    for key, group in groups.items():
        winner = sorted(group, key=_video_sort_key)[0]
        kept_by_identity.add(id(winner))
        if len(group) <= 1:
            continue
        for item in group:
            if item is winner:
                continue
            dropped.append(
                {
                    "name": item.get("name"),
                    "path": item.get("path"),
                    "size": int(item.get("size") or 0),
                    "dedupe_group_key": key,
                    "kept_name": winner.get("name"),
                    "reason": "duplicate_quality_smaller_size",
                }
            )

    kept = [video for video in videos if id(video) in kept_by_identity]
    return kept, dropped
```

Review `SEPARATOR_PATTERN` spacing after insertion and format it as:

```python
SEPARATOR_PATTERN = re.compile(r"[\s._\-\[\]()]+")
```

- [ ] **Step 8: Run all policy helper tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_is_vr_movie_tags_matches_only_clear_vr_tags backend/tests/test_storage_worker_pipeline.py::test_insert_vr_directory_before_code_folder_without_duplication backend/tests/test_storage_worker_pipeline.py::test_quality_dedupe_key_removes_quality_tokens_but_preserves_parts backend/tests/test_storage_worker_pipeline.py::test_dedupe_quality_variants_keeps_largest_per_group -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

Run:

```bash
git add backend/app/modules/storage/tasks/policies.py backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: add storage vr and quality policies"
```

Expected: commit succeeds and includes only Task 1 files.

---

### Task 2: VR Target Path Planning

**Files:**
- Modify: `backend/app/modules/storage/worker/target_planning.py`
- Modify: `backend/app/modules/storage/worker/steps.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Consumes:
  - `is_vr_movie_tags(tags: list[str]) -> bool`
  - `insert_vr_directory(target_path: str, code_folder: str) -> str`
- Produces:
  - `plan_storage_attempt(subtask, config: dict, magnet: dict, movie_tags: list[str] | None = None) -> StorageAttemptPlan`
  - `execute_current_magnet_attempt(context, magnet: dict, movie_tags: list[str] | None = None) -> bool`

- [ ] **Step 1: Write failing target planning tests**

Append these tests to `backend/tests/test_storage_worker_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run target planning tests to verify they fail**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_inserts_vr_for_movie_tags_only backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_ignores_magnet_vr_tags_for_target_path backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_vr_multiple_targets_without_duplicate_vr -v
```

Expected: FAIL because `plan_storage_attempt` does not accept `movie_tags` and does not insert `VR`.

- [ ] **Step 3: Update target planning implementation**

Modify `backend/app/modules/storage/worker/target_planning.py`:

```python
from backend.app.modules.storage.tasks.policies import (
    build_video_filename,
    code_folder_from_filename,
    insert_vr_directory,
    is_vr_movie_tags,
)
```

Change the function signature and add VR path handling:

```python
def plan_storage_attempt(subtask, config: dict, magnet: dict, movie_tags: list[str] | None = None) -> StorageAttemptPlan:
    tags = list(magnet.get("tags") or [])
    download_root = config.get("download_root_folder", "/Downloads")
    download_folder = f"{download_root}/storage_{subtask.id}"
    preview_name = build_video_filename(subtask.movie_code, f"{subtask.movie_code}.mp4", tags, 0, 1)
    code_folder = code_folder_from_filename(preview_name)
    target_root = config.get("target_folder", "/Movies")
    target_locations = list(subtask.target_locations or [])
    selected_location = getattr(subtask, "selected_storage_location", None) or ""
    if selected_location:
        target_paths = [f"{target_root}/{selected_location}/{code_folder}"]
    else:
        target_paths = [f"{target_root}/{location}/{code_folder}" for location in target_locations] or [f"{target_root}/{code_folder}"]
    if is_vr_movie_tags(list(movie_tags or [])):
        target_paths = [insert_vr_directory(path, code_folder) for path in target_paths]
    subtask.download_path = download_folder
    subtask.target_paths = target_paths
    return StorageAttemptPlan(
        download_root=download_root,
        download_folder=download_folder,
        preview_name=preview_name,
        code_folder=code_folder,
        target_root=target_root,
        target_paths=target_paths,
    )
```

- [ ] **Step 4: Run target planning tests to verify they pass**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_inserts_vr_for_movie_tags_only backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_ignores_magnet_vr_tags_for_target_path backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_vr_multiple_targets_without_duplicate_vr -v
```

Expected: PASS.

- [ ] **Step 5: Write failing test that movie tags flow through `execute_subtask_pipeline`**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
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
```

- [ ] **Step 6: Run movie tag flow test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_passes_movie_tags_to_attempt -v
```

Expected: FAIL because `execute_subtask_pipeline` calls `execute_current_magnet_attempt(context, magnet)` without `movie_tags`.

- [ ] **Step 7: Update `steps.py` to pass movie tags**

Modify `backend/app/modules/storage/worker/steps.py`:

```python
def execute_current_magnet_attempt(context, magnet: dict, movie_tags: list[str] | None = None) -> bool:
```

Change path planning:

```python
plan = plan_storage_attempt(subtask, config, magnet, movie_tags=movie_tags)
```

Add VR context to the prepare log without changing the existing message:

```python
prepare_context = {"download_path": download_folder, "target_paths": target_paths, "magnet_id": magnet.get("id")}
if any(isinstance(tag, str) and tag.strip().lower() == "vr" for tag in (movie_tags or [])):
    prepare_context.update({"vr_detected": True, "vr_source": "movie_tags"})
context.log(
    "INFO",
    f"准备完成: download={download_folder}, target={target_paths[-1]}, targets={target_paths}, suffix={preview_name.replace(subtask.movie_code.upper(), '').rsplit('.', 1)[0]}",
    prepare_context,
    step="prepare",
)
```

At the top of `steps.py`, import the helper used for logging consistency:

```python
from backend.app.modules.storage.tasks.policies import is_vr_movie_tags
```

Then use it in the log block:

```python
if is_vr_movie_tags(list(movie_tags or [])):
    prepare_context.update({"vr_detected": True, "vr_source": "movie_tags"})
```

In `execute_subtask_pipeline`, change:

```python
success = execute_current_magnet_attempt(context, magnet)
```

to:

```python
success = execute_current_magnet_attempt(context, magnet, movie_tags=list(movie.tags or []))
```

- [ ] **Step 8: Run Task 2 tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_inserts_vr_for_movie_tags_only backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_ignores_magnet_vr_tags_for_target_path backend/tests/test_storage_worker_pipeline.py::test_plan_storage_attempt_vr_multiple_targets_without_duplicate_vr backend/tests/test_storage_worker_pipeline.py::test_execute_subtask_pipeline_passes_movie_tags_to_attempt -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add backend/app/modules/storage/worker/target_planning.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: route vr movies into vr storage folders"
```

Expected: commit succeeds and includes only Task 2 files.

---

### Task 3: Quality Dedupe Pipeline Integration

**Files:**
- Modify: `backend/app/modules/storage/worker/file_pipeline.py`
- Test: `backend/tests/test_storage_worker_pipeline.py`

**Interfaces:**
- Consumes:
  - `dedupe_quality_variants(videos: list[dict]) -> tuple[list[dict], list[dict]]`
- Produces:
  - `run_found_files_pipeline(...)` filters duplicate quality variants before calling `rename_selected_videos`.

- [ ] **Step 1: Write failing pipeline integration test**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run pipeline integration test to verify it fails**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_run_found_files_pipeline_dedupes_quality_variants_before_rename -v
```

Expected: FAIL because both quality variants are passed to `rename_selected_videos`.

- [ ] **Step 3: Integrate dedupe into file pipeline**

Modify `backend/app/modules/storage/worker/file_pipeline.py` imports:

```python
from backend.app.modules.storage.tasks.policies import dedupe_quality_variants
```

After the existing `classified = classify_scanned_files(scanned, config)` log and before the empty selected-videos check, add:

```python
selected_videos, dropped_quality_variants = dedupe_quality_variants(classified.selected_videos)
if dropped_quality_variants:
    context.log(
        "INFO",
        "清晰度重复筛选",
        {
            "kept_files": [
                {"name": item.get("name"), "path": item.get("path"), "size": int(item.get("size") or 0)}
                for item in selected_videos
            ],
            "dropped_files": dropped_quality_variants,
        },
        step="select_videos",
    )
else:
    selected_videos = classified.selected_videos
```

Change the empty check and rename call from `classified.selected_videos` to `selected_videos`:

```python
if not selected_videos:
    context.log("WARNING", "扫描到文件但未识别到主视频", {"magnet_id": magnet.get("id"), "file_count": len(scanned)}, step="select_videos")
    return False

context.set_step("rename_files")
renamed_files = rename_selected_videos(context, selected_videos, tags)
```

- [ ] **Step 4: Run pipeline integration test to verify it passes**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_run_found_files_pipeline_dedupes_quality_variants_before_rename -v
```

Expected: PASS.

- [ ] **Step 5: Run full storage worker pipeline test file**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add backend/app/modules/storage/worker/file_pipeline.py backend/tests/test_storage_worker_pipeline.py
git commit -m "feat: dedupe storage quality variants before rename"
```

Expected: commit succeeds and includes only Task 3 files.

---

### Task 4: Final Verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes all prior task outputs.
- Produces verified working tree ready for review.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 2: Check git status**

Run:

```bash
git status --short
```

Expected: no unstaged changes from the storage implementation. Pre-existing unrelated crawler changes may still appear and must not be modified or reverted.

- [ ] **Step 3: Review final diff**

Run:

```bash
git log --oneline -4
git diff --stat HEAD~3..HEAD
```

Expected: the last three implementation commits correspond to policy helpers, VR target routing, and quality dedupe integration.

---

## Self-Review

- Spec coverage: VR target paths, movie-only VR tags, magnet tags excluded from VR detection, quality token dedupe, multi-part preservation, logging, non-fatal bad data behavior, and backend tests are covered by Tasks 1-3.
- Placeholder scan: this plan contains no placeholder implementation steps.
- Type consistency: helper signatures produced by Task 1 are consumed unchanged by Tasks 2 and 3.
