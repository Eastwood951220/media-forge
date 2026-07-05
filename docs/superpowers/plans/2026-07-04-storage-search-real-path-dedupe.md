# Storage Search Real Path Dedupe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure CloudDrive2 search results are converted to real paths with `GetOriginalPath`, deduplicated by real path, and never renamed or moved through `[Search]` virtual paths.

**Architecture:** Keep the existing storage worker flow and scoped search API. Strengthen `backend/app/modules/storage/worker/file_finder.py` so every virtual search result is normalized before filtering, rejected when it cannot resolve to a real path, and deduplicated by resolved real path. Add regression tests proving a single real file discovered through multiple search aliases produces one accepted file and a non-CD filename.

**Tech Stack:** Python 3.12, FastAPI backend modules, CloudDrive2 gateway abstraction, JSONL storage task logs, Pytest.

---

## Source Spec

Approved design: `docs/superpowers/specs/2026-07-04-storage-search-real-path-dedupe-design.md`

The implementation must preserve these decisions:

- Search result paths under `[Search]` must call `provider.get_original_path`.
- `accepted_files` must never contain `[Search]`.
- Missing original paths are rejected with `missing_original_path`.
- Original paths that still contain `[Search]` are rejected with `virtual_search_path`.
- Multiple entries resolving to the same real path are deduplicated and rejected as `duplicate_resolved_path`.
- A single real accepted file must be renamed without `-CD1`, `-CD2`, or `-CD3`.

## File Structure

- Modify `backend/app/modules/storage/worker/file_finder.py`: Real-path normalization, rejection metadata, duplicate detection by resolved path, and cleanup of unreachable code.
- Modify `backend/tests/test_storage_file_finder_scope.py`: Existing scoped-search expectations and new real-path dedupe tests.
- Modify `backend/tests/test_storage_worker_pipeline.py`: One end-to-end naming regression that proves deduped one-file input does not generate a CD suffix.

## Task 1: Add Real-Path Dedupe Regression Tests

**Files:**
- Modify: `backend/tests/test_storage_file_finder_scope.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Update existing scoped-search expectations to include raw and resolved paths**

In `backend/tests/test_storage_file_finder_scope.py`, update the `rejected_files` expectation in `test_scoped_search_logs_raw_resolved_accepted_and_rejected_files` to:

```python
    assert result.log_context["rejected_files"] == [
        {
            "name": "MIDA-628.mp4",
            "raw_path": "/Search/MIDA-628.mp4",
            "resolved_path": "/Downloads/storage_old/MIDA-628.mp4",
            "size": 524288000,
            "reason": "movie_code_mismatch",
        },
        {
            "name": "ACZD-165.txt",
            "raw_path": "/Downloads/storage_sub/ACZD-165.txt",
            "resolved_path": "/Downloads/storage_sub/ACZD-165.txt",
            "size": 1024,
            "reason": "extension_not_allowed",
        },
    ]
```

Update the `rejected_files` expectation in `test_root_recovery_rejects_other_movie_codes` to:

```python
    assert result.log_context["rejected_files"] == [
        {
            "name": "CHERD-105.mp4",
            "raw_path": "/Search/CHERD-105.mp4",
            "resolved_path": "/Downloads/storage_old/CHERD-105/CHERD-105.mp4",
            "size": 943718400,
            "reason": "movie_code_mismatch",
        }
    ]
```

- [ ] **Step 2: Add a test that virtual search results require GetOriginalPath**

Append this test to `backend/tests/test_storage_file_finder_scope.py`:

```python
class DuplicateVirtualPathProvider:
    def __init__(self) -> None:
        self.original_path_calls: list[str] = []
        self.original_paths = {
            "/Downloads/storage_sub/[Search]ACZD-165/hhd800.com@ACZD-165.mp4": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "/Downloads/storage_sub/[Search]ACZD-165/ACZD-165/hhd800.com@ACZD-165.mp4": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
        }

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        return [
            FakeRemoteFile(
                "hhd800.com@ACZD-165.mp4",
                "/Downloads/storage_sub/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
                4770615244,
                False,
                True,
            ),
            FakeRemoteFile(
                "hhd800.com@ACZD-165.mp4",
                "/Downloads/storage_sub/[Search]ACZD-165/ACZD-165/hhd800.com@ACZD-165.mp4",
                4770615244,
                False,
                True,
            ),
            FakeRemoteFile(
                "hhd800.com@ACZD-165.mp4",
                "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
                4770615244,
                False,
                False,
            ),
        ]

    def get_original_path(self, path):
        self.original_path_calls.append(path)
        return self.original_paths.get(path, "")

    def list_files(self, path, force_refresh=False):
        return []


def test_scoped_search_uses_original_path_and_dedupes_virtual_aliases() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    provider = DuplicateVirtualPathProvider()

    result = find_scoped_video_files(
        provider=provider,
        search_terms=["ACZD-165"],
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.original_path_calls == [
        "/Downloads/storage_sub/[Search]ACZD-165/hhd800.com@ACZD-165.mp4",
        "/Downloads/storage_sub/[Search]ACZD-165/ACZD-165/hhd800.com@ACZD-165.mp4",
    ]
    assert result.accepted_files == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "is_dir": False,
        }
    ]
    assert "/[Search]" not in result.accepted_files[0]["path"]
    assert result.log_context["rejected_files"] == [
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "raw_path": "/Downloads/storage_sub/[Search]ACZD-165/ACZD-165/hhd800.com@ACZD-165.mp4",
            "resolved_path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "reason": "duplicate_resolved_path",
        },
        {
            "name": "hhd800.com@ACZD-165.mp4",
            "raw_path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "resolved_path": "/Downloads/storage_sub/ACZD-165/hhd800.com@ACZD-165.mp4",
            "size": 4770615244,
            "reason": "duplicate_resolved_path",
        },
    ]
```

- [ ] **Step 3: Add tests for missing and still-virtual original paths**

Append this test to `backend/tests/test_storage_file_finder_scope.py`:

```python
class InvalidOriginalPathProvider:
    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        return [
            FakeRemoteFile("ACZD-165-empty.mp4", "/Downloads/storage_sub/[Search]empty.mp4", 500 * 1024 * 1024, False, True),
            FakeRemoteFile("ACZD-165-virtual.mp4", "/Downloads/storage_sub/[Search]virtual.mp4", 500 * 1024 * 1024, False, True),
        ]

    def get_original_path(self, path):
        if path.endswith("empty.mp4"):
            return ""
        return "/Downloads/storage_sub/[Search]still-virtual/ACZD-165-virtual.mp4"

    def list_files(self, path, force_refresh=False):
        return []


def test_scoped_search_rejects_missing_and_virtual_original_paths() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    result = find_scoped_video_files(
        provider=InvalidOriginalPathProvider(),
        search_terms=["ACZD-165"],
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert result.accepted_files == []
    assert result.log_context["rejected_files"] == [
        {
            "name": "ACZD-165-empty.mp4",
            "raw_path": "/Downloads/storage_sub/[Search]empty.mp4",
            "resolved_path": "",
            "size": 524288000,
            "reason": "missing_original_path",
        },
        {
            "name": "ACZD-165-virtual.mp4",
            "raw_path": "/Downloads/storage_sub/[Search]virtual.mp4",
            "resolved_path": "/Downloads/storage_sub/[Search]still-virtual/ACZD-165-virtual.mp4",
            "size": 524288000,
            "reason": "virtual_search_path",
        },
    ]
```

- [ ] **Step 4: Add a naming regression for deduped one-file input**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
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
```

- [ ] **Step 5: Run the new tests and verify failure**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py::test_scoped_search_uses_original_path_and_dedupes_virtual_aliases backend/tests/test_storage_file_finder_scope.py::test_scoped_search_rejects_missing_and_virtual_original_paths backend/tests/test_storage_worker_pipeline.py::test_deduped_single_real_file_renames_without_cd_suffix -v
```

Expected: FAIL in the scoped search tests because current search accepts unresolved virtual paths and does not report `duplicate_resolved_path`, `missing_original_path`, or `virtual_search_path`. The naming regression should pass and documents the expected downstream behavior after dedupe.

- [ ] **Step 6: Commit failing tests**

```bash
git add backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: cover storage search real path dedupe"
```

## Task 2: Normalize Search Results to Real Paths

**Files:**
- Modify: `backend/app/modules/storage/worker/file_finder.py`
- Test: `backend/tests/test_storage_file_finder_scope.py`

- [ ] **Step 1: Replace `_file_to_dict` and remove unreachable old code**

In `backend/app/modules/storage/worker/file_finder.py`, replace `_file_to_dict` with these helpers:

```python
def _is_virtual_search_path(path: str) -> bool:
    return "/[Search]" in str(PurePosixPath(path))


def _is_search_result(file_obj, raw_item: dict) -> bool:
    return bool(
        getattr(file_obj, "is_search_result", False)
        or getattr(file_obj, "isSearchResult", False)
        or _is_virtual_search_path(raw_item["path"])
    )


def _resolve_file_candidate(provider, file_obj) -> tuple[dict, dict, str | None]:
    raw_item = _raw_file_to_dict(file_obj)
    resolved_item = dict(raw_item)
    if not _is_search_result(file_obj, raw_item):
        if _is_virtual_search_path(raw_item["path"]):
            return raw_item, resolved_item, "virtual_search_path"
        return raw_item, resolved_item, None

    try:
        original = provider.get_original_path(raw_item["path"])
    except Exception:
        original = ""
    if not original:
        resolved_item["path"] = ""
        return raw_item, resolved_item, "missing_original_path"
    resolved_item["path"] = original
    resolved_item["name"] = PurePosixPath(original).name
    if _is_virtual_search_path(original):
        return raw_item, resolved_item, "virtual_search_path"
    return raw_item, resolved_item, None


def _file_to_dict(provider, file_obj) -> dict:
    raw_item, resolved_item, reason = _resolve_file_candidate(provider, file_obj)
    if reason is not None:
        return {
            **resolved_item,
            "resolution_error": reason,
            "raw_path": raw_item["path"],
            "resolved_path": resolved_item["path"],
        }
    return resolved_item
```

- [ ] **Step 2: Add a rejected-candidate helper with raw and resolved paths**

Add below `_rejection_reason`:

```python
def _rejected_file(raw_item: dict, resolved_item: dict, reason: str, error: str | None = None) -> dict:
    entry = {
        "name": raw_item["name"],
        "raw_path": raw_item["path"],
        "resolved_path": resolved_item.get("path", ""),
        "size": int(raw_item.get("size") or 0),
        "reason": reason,
    }
    if error:
        entry["error"] = error
    return entry
```

- [ ] **Step 3: Replace `_append_candidate` with raw/resolved-aware duplicate detection**

Replace `_append_candidate` with:

```python
def _append_candidate(
    *,
    raw_candidate: dict,
    candidate: dict,
    accepted: list[dict],
    rejected: list[dict],
    seen: set[str],
    config: dict,
    movie_code: str,
    search_scope: str,
    task_download_folder: str,
    resolution_error: str | None = None,
) -> None:
    if candidate.get("is_dir"):
        return
    if resolution_error is not None:
        rejected.append(_rejected_file(raw_candidate, candidate, resolution_error))
        return
    reason = _rejection_reason(
        candidate,
        config=config,
        movie_code=movie_code,
        search_scope=search_scope,
        task_download_folder=task_download_folder,
    )
    if reason:
        rejected.append(_rejected_file(raw_candidate, candidate, reason))
        return
    if _is_virtual_search_path(candidate["path"]):
        rejected.append(_rejected_file(raw_candidate, candidate, "virtual_search_path"))
        return
    if candidate["path"] in seen:
        rejected.append(_rejected_file(raw_candidate, candidate, "duplicate_resolved_path"))
        return
    seen.add(candidate["path"])
    accepted.append({
        "name": candidate["name"],
        "path": candidate["path"],
        "size": int(candidate.get("size") or 0),
        "is_dir": False,
    })
```

- [ ] **Step 4: Update `find_scoped_video_files` to use normalized candidates**

In the loop over `search_results`, replace:

```python
        raw_item = _raw_file_to_dict(file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved = _file_to_dict(provider, file_obj)
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        _append_candidate(
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )
```

with:

```python
        raw_item, resolved, resolution_error = _resolve_file_candidate(provider, file_obj)
        raw_results.append({key: raw_item[key] for key in ("name", "path", "size")})
        resolved_results.append({key: resolved[key] for key in ("name", "path", "size")})
        _append_candidate(
            raw_candidate=raw_item,
            candidate=resolved,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
            resolution_error=resolution_error,
        )
```

- [ ] **Step 5: Update the recursive-list loop to use raw and resolved entries**

In the loop over `listed_files`, replace the `_append_candidate` call with:

```python
        _append_candidate(
            raw_candidate=listed,
            candidate=listed,
            accepted=accepted,
            rejected=rejected,
            seen=seen,
            config=config,
            movie_code=movie_code,
            search_scope=search_scope,
            task_download_folder=task_download_folder,
        )
```

- [ ] **Step 6: Run scoped search tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit real-path normalization**

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/tests/test_storage_file_finder_scope.py
git commit -m "fix: dedupe storage search results by real path"
```

## Task 3: Guard Downstream Search Results and Naming

**Files:**
- Modify: `backend/app/modules/storage/worker/steps.py`
- Modify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Add a guard that logs and rejects virtual paths before scanning**

In `backend/app/modules/storage/worker/steps.py`, replace `scan_found_files` with:

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
        if not file.get("is_dir", False) and "/[Search]" not in str(file.get("path", ""))
    ]
```

This guard is intentionally redundant. `file_finder.py` is the primary protection; `scan_found_files` prevents future callers from accidentally passing virtual paths downstream.

- [ ] **Step 2: Add a pipeline test for the scan guard**

Append this test to `backend/tests/test_storage_worker_pipeline.py`:

```python
def test_scan_found_files_rejects_virtual_search_paths() -> None:
    from backend.app.modules.storage.worker.steps import scan_found_files

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
```

- [ ] **Step 3: Run downstream tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_worker_pipeline.py::test_scan_found_files_rejects_virtual_search_paths backend/tests/test_storage_worker_pipeline.py::test_deduped_single_real_file_renames_without_cd_suffix -v
```

Expected: PASS.

- [ ] **Step 4: Commit downstream guard**

```bash
git add backend/app/modules/storage/worker/steps.py backend/tests/test_storage_worker_pipeline.py
git commit -m "fix: prevent virtual search paths from scanning"
```

## Task 4: Full Verification

**Files:**
- Verify: `backend/app/modules/storage/worker/file_finder.py`
- Verify: `backend/app/modules/storage/worker/steps.py`
- Verify: `backend/tests/test_storage_file_finder_scope.py`
- Verify: `backend/tests/test_storage_worker_pipeline.py`

- [ ] **Step 1: Run targeted storage tests**

Run:

```bash
source .venv/bin/activate
python -m pytest backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py backend/tests/test_storage_worker_timeline.py backend/tests/test_storage_realtime_events.py -v
```

Expected: PASS.

- [ ] **Step 2: Verify accepted files cannot contain virtual paths**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
from backend.app.modules.storage.worker.file_finder import _is_virtual_search_path
assert _is_virtual_search_path('/Downloads/storage_sub/[Search]ACZD-165/file.mp4') is True
assert _is_virtual_search_path('/Downloads/storage_sub/ACZD-165/file.mp4') is False
print('virtual path guard ok')
PY
```

Expected output:

```text
virtual path guard ok
```

- [ ] **Step 3: Verify no unreachable old code remains**

Run:

```bash
python - <<'PY'
from pathlib import Path
body = Path('backend/app/modules/storage/worker/file_finder.py').read_text(encoding='utf-8')
assert 'return item\n    path = getattr(file_obj' not in body
print('file_finder cleanup ok')
PY
```

Expected output:

```text
file_finder cleanup ok
```

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat HEAD
git diff -- backend/app/modules/storage/worker/file_finder.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
```

Expected: The diff only changes real-path normalization, virtual-path rejection, dedupe logging, scan guarding, and related backend tests.

- [ ] **Step 5: Commit verification fixes if files changed**

If Task 4 changed files, run:

```bash
git add backend/app/modules/storage/worker/file_finder.py backend/app/modules/storage/worker/steps.py backend/tests/test_storage_file_finder_scope.py backend/tests/test_storage_worker_pipeline.py
git commit -m "test: verify storage real path dedupe"
```

If Task 4 did not change files, do not create a commit.

## Self-Review

- Spec coverage: The plan enforces `GetOriginalPath`, rejects missing or still-virtual original paths, deduplicates by real path, and prevents virtual paths from reaching scan and rename.
- Root cause coverage: The logged three-path `ACZD-165` duplicate case becomes one accepted file and two `duplicate_resolved_path` rejections.
- Naming coverage: A deduped single real file produces `ACZD-165.mp4`, while real multi-file sets still use existing `-CD` naming.
- Scope control: The plan does not change CloudDrive2 gateway signatures, magnet ordering, UI, or filename rules for true multi-file videos.
