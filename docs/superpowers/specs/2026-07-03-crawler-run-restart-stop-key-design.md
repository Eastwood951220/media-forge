# Crawler Run Restart Stop Key Design

## Problem

Crawler runs are restarted in place, reusing the same `crawl_runs.id`. Stopping a run writes a Redis stop flag at `media-forge:crawler:stop:{run_id}` through `CrawlerRuntimeState.request_stop()`. The current restart path requeues the same run ID without clearing that flag, so the worker's `stop_check` immediately returns `True`.

Observed symptom:

```text
[3333] 开始处理详情页: 共 27 条
[3333] 详情页 1/27 收到停止信号
```

The restart API returns `201 Created`, but the run stops immediately because it inherits the old stop signal.

## Goals

- Restarting an in-place crawler run must clear the old stop signal before the run is enqueued.
- Finished worker lifecycle must clear the stop signal as a safety net.
- Queue status should not report `stop_requested=true` for a restarted run unless a new stop request is made.
- The fix must not change crawler collection/detail retry semantics.

## Non-Goals

- Do not create a new `crawl_runs` row on restart.
- Do not change list-stage versus detail-stage restart behavior.
- Do not change how child tasks are reset or filtered for retry.
- Do not alter logs, movie persistence, or task deletion behavior.

## Design

Add `CrawlerRuntimeState.clear_stop(run_id)` to delete only the stop key for that run:

```python
def clear_stop(self, run_id: str) -> None:
    self.redis.delete(self._stop_key(run_id))
```

Use it in two places:

1. `CrawlerRunService.restart_run()` calls `self.runtime.clear_stop(str(run.id))` immediately before `enqueue_run(str(run.id))`.
2. `process_run()` calls `runtime.clear_stop(run_id)` in its `finally` block, alongside `runtime.set_current_run(None)` and `runtime.write_progress(run_id, {})`.

Restart still mutates and requeues the same run row. Clearing the stop key is runtime-state cleanup only; it does not modify database status beyond the existing restart flow.

## Data Flow

Stop flow:

```text
POST /api/crawler/runs/{id}/stop
  -> runtime.request_stop(id)
  -> run.status = stopped
```

Restart flow:

```text
POST /api/crawler/runs/{id}/restart
  -> reset run row to queued
  -> runtime.clear_stop(id)
  -> runtime.enqueue_run(id)
  -> worker starts
  -> stop_check reads false unless a new stop request arrives
```

Worker completion flow:

```text
process_run(...)
  -> execute run
  -> finally:
       runtime.set_current_run(None)
       runtime.write_progress(run_id, {})
       runtime.clear_stop(run_id)
```

## Tests

Backend runtime state:

- `test_clear_stop_signal()` in `backend/tests/test_crawler_runtime_redis.py`
- Assert `request_stop("run-1")` makes `is_stop_requested("run-1")` true.
- Assert `clear_stop("run-1")` makes `is_stop_requested("run-1")` false.

Backend restart API/service:

- Extend the restart test in `backend/tests/test_crawler_runs_api.py` or add a new focused test.
- Use a fake runtime that records `clear_stop` and `enqueue_run`.
- Assert `restart_run()` calls `clear_stop(run_id)` before or at least during restart before the run is processed.
- Assert the returned run ID is the original run ID.

Worker lifecycle:

- Add or extend a worker test in `backend/tests/test_crawler_worker_service.py`.
- Use a runtime fake that has a stop flag set before processing.
- After `process_next_run()` or `process_run()` finishes, assert `clear_stop(run_id)` was called.

## Error Handling

If Redis delete succeeds normally, restart proceeds. If Redis itself is unavailable, the existing runtime path already fails around queue operations; this design does not introduce a separate recovery path. The restart API should continue to surface runtime failures through the existing `503` handling in `restart_run()`'s router.

## Acceptance Criteria

- Restarting a previously stopped in-place run no longer immediately logs `收到停止信号`.
- `GET /api/crawler/runs/queue-status` does not report `stop_requested=true` for a restarted run unless the user clicks stop again.
- Stop still works during an active restarted run.
- Existing list-stage/detail-stage restart behavior remains unchanged.
