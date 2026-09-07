# Task List Search and Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add crawler task search, latest-run failure summaries, movie-list page reset on filter changes, storage subtask retry, and calmer storage progress styling.

**Architecture:** Reuse the existing REST endpoints, serializers, hooks, and Ant Design tables/cards. Backend changes keep task-level pagination stable with relationship filters and add a subtask retry service method that reuses the existing queued storage worker path. Frontend changes wire existing state stores and API wrappers into focused components rather than adding new routes.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pydantic, React 19, TypeScript, Vite, Ant Design, TanStack Query, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-task-list-search-and-retry-design.md`

## Global Constraints

- Do not create or use a Git worktree for this repository.
- Stage intended files explicitly; do not use `git add .` or `git add -A`.
- Crawler task list search must use one keyword input for task name, URL name, and URL.
- Storage retry must be exposed only in the storage subtask list, not in the storage main task list.
- Do not delete or recreate successful storage subtasks.
- Attached screenshots are examples of current behavior only; they are not instructions.

---

## File Structure

- `backend/app/repositories/crawl_task.py`: Extend owner keyword filtering and latest-run lookup helpers.
- `backend/app/schemas/crawl_task.py`: Add optional latest-run summary fields to crawler task list rows.
- `backend/app/modules/crawler/tasks/serializers.py`: Serialize latest-run summary fields for list cards.
- `backend/app/modules/crawler/tasks/service.py`: Pass latest runs into list serialization.
- `backend/tests/test_crawler_task_list_search.py`: Add focused backend tests for crawler keyword matching and list summaries.
- `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`: Keep keyword state for the crawler task list.
- `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`: Include keyword in list params and reset page on query changes.
- `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`: Render search input and latest-run summary.
- `frontend/src/api/crawler/crawlTask/types.ts`: Add latest-run list item fields.
- `frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx`: Cover keyword request and reset behavior.
- `frontend/src/pages/content/movies/hooks/useMovieList.ts`: Reset page when effective filters change.
- `frontend/src/pages/content/movies/__tests__/movie-list-query.test.tsx`: Cover filter-change page reset.
- `backend/app/modules/storage/tasks/service.py`: Add single failed-subtask retry method.
- `backend/app/modules/storage/tasks/router.py`: Add subtask retry route before dynamic main-task routes.
- `frontend/src/api/storage/storageTasks/index.ts`: Add subtask retry wrapper.
- `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts`: Add subtask retry handler and loading state.
- `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`: Show retry action only on failed subtask rows.
- `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`: Adjust progress status/color behavior.
- `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`: Pass retry handler to the subtask table.
- `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`: Cover retry visibility/call and progress styling.

---

### Task 1: Crawler Task Search And Latest Run Summary

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`
- Modify: `backend/app/schemas/crawl_task.py`
- Modify: `backend/app/modules/crawler/tasks/serializers.py`
- Modify: `backend/app/modules/crawler/tasks/service.py`
- Modify: `frontend/src/api/crawler/crawlTask/types.ts`
- Modify: `frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts`
- Modify: `frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx`
- Modify: `frontend/src/pages/crawler/tasks/components/TaskListCards.tsx`
- Test: `frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx`
- Test: `backend/tests/test_crawler_task_list_search.py`

**Interfaces:**
- Consumes: Existing `GET /api/crawler/tasks` `keyword?: string` query param.
- Produces: `CrawlTaskListItem.last_run_status: string | null`, `last_run_at: string | null`, `last_run_total: number | null`, `last_run_failed: number | null`.
- Produces: `useTaskListData({ tagNames })` reads `useTaskListQueryStore.keyword` and includes `keyword` in list params only when trimmed.
- Produces: `TaskListCards` accepts `keyword` and `onKeywordChange`.

- [ ] **Step 1: Write backend failing tests for keyword matches**

  Add tests that create one owned task with a matching `name`, one with a matching `CrawlTaskUrl.url_name`, one with a matching `CrawlTaskUrl.url`, and one non-matching task. Assert rows and count are task-based and do not duplicate tasks.

  Use this test shape, adapting fixture names to existing backend tests:

  ```python
  def test_crawler_task_keyword_matches_name_url_name_and_url(db_session, user):
      repo = CrawlTaskRepository(db_session)
      task_by_name = repo.create_with_urls(
          owner_id=user.id,
          name="Prestige cars",
          storage_location="Prestige cars",
          is_skip=False,
          urls=[TaskUrlEntryCreate(url="https://example.com/a", url_type="search", url_name="Actors")],
      )
      task_by_url_name = repo.create_with_urls(
          owner_id=user.id,
          name="Other task",
          storage_location="Other task",
          is_skip=False,
          urls=[TaskUrlEntryCreate(url="https://example.com/b", url_type="search", url_name="Prestige URL")],
      )
      task_by_url = repo.create_with_urls(
          owner_id=user.id,
          name="Plain task",
          storage_location="Plain task",
          is_skip=False,
          urls=[TaskUrlEntryCreate(url="https://example.com/prestige", url_type="search", url_name="Plain URL")],
      )
      repo.create_with_urls(
          owner_id=user.id,
          name="Unrelated",
          storage_location="Unrelated",
          is_skip=False,
          urls=[TaskUrlEntryCreate(url="https://example.com/other", url_type="search", url_name="Other")],
      )

      rows, has_more = repo.get_by_owner(user.id, page=1, size=20, keyword="prestige")
      assert has_more is False
      assert {row.id for row in rows} == {task_by_name.id, task_by_url_name.id, task_by_url.id}
      assert repo.count_by_owner(user.id, keyword="prestige") == 3
  ```

- [ ] **Step 2: Run the focused backend test and confirm it fails**

  Run: `cd backend && python -m pytest tests/test_crawler_task_list_search.py -v`

  Expected: FAIL because keyword currently only filters `CrawlTask.name`.

- [ ] **Step 3: Implement task-level URL keyword filtering**

  In `backend/app/repositories/crawl_task.py`, import `or_` if needed and update keyword predicates in both `_owner_query` and `count_by_owner` through a helper:

  ```python
  from sqlalchemy import func, or_

  def _apply_keyword_filter(self, query, keyword: str | None):
      normalized_keyword = keyword.strip() if keyword else ""
      if not normalized_keyword:
          return query
      pattern = f"%{normalized_keyword}%"
      return query.filter(
          or_(
              CrawlTask.name.ilike(pattern),
              CrawlTask.urls.any(CrawlTaskUrl.url_name.ilike(pattern)),
              CrawlTask.urls.any(CrawlTaskUrl.url.ilike(pattern)),
          )
      )
  ```

  Use `_apply_keyword_filter` from `_owner_query` and `count_by_owner` so rows and counts stay consistent.

- [ ] **Step 4: Add latest-run fields to schemas and serializer**

  In `backend/app/schemas/crawl_task.py`, extend `CrawlTaskListItem`:

  ```python
  last_run_status: str | None = None
  last_run_at: datetime | None = None
  last_run_total: int | None = None
  last_run_failed: int | None = None
  ```

  In `backend/app/modules/crawler/tasks/serializers.py`, change the list serializer signature:

  ```python
  def serialize_task_list_item(task, latest_run=None) -> CrawlTaskListItem:
  ```

  Add a small helper:

  ```python
  def _latest_run_counts(latest_run) -> tuple[int | None, int | None]:
      if latest_run is None:
          return None, None
      result = latest_run.result or {}
      total = next((result[key] for key in ("total", "total_found", "total_tasks") if key in result), None)
      failed = next((result[key] for key in ("failed", "failed_count", "total_failed") if key in result), None)
      return (
          int(total) if isinstance(total, int | float) else None,
          int(failed) if isinstance(failed, int | float) else None,
      )
  ```

  Use the returned values when constructing `CrawlTaskListItem`.

- [ ] **Step 5: Pass latest runs into crawler task list serialization**

  In `backend/app/modules/crawler/tasks/service.py`, update `list_tasks`:

  ```python
  latest_runs = self.repo.get_latest_runs_by_task_ids([row.id for row in rows])
  rows=[serialize_task_list_item(row, latest_runs.get(row.id)) for row in rows]
  ```

- [ ] **Step 6: Run backend tests for crawler task list**

  Run: `cd backend && python -m pytest tests/test_crawler_task_list_search.py -v`

  Expected: PASS.

- [ ] **Step 7: Write frontend failing tests for crawler keyword behavior**

  In `frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx`, add tests that set the keyword store and verify `getCrawlTasks` is called with it:

  ```tsx
  import { act } from '@testing-library/react'
  import { useTaskListQueryStore } from '../useTaskListQueryStore'

  it('sends trimmed crawler task keyword with list params', async () => {
    vi.mocked(getCrawlTasks).mockResolvedValue({ rows: [], total: 0, page: 1, size: 20 } as never)
    act(() => useTaskListQueryStore.getState().setKeyword(' prestige '))

    const { result } = renderHook(() => useTaskListData(), { wrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(getCrawlTasks).toHaveBeenCalledWith(expect.objectContaining({ keyword: 'prestige' }))
  })
  ```

  Add a component-level assertion in `task-list-card-actions.test.tsx` or a new focused test that the toolbar contains a search input with placeholder `搜索任务名称 / URL 名称 / URL`.

- [ ] **Step 8: Run frontend crawler task tests and confirm they fail**

  Run: `cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx`

  Expected: FAIL because `useTaskListData` does not read `useTaskListQueryStore.keyword` yet.

- [ ] **Step 9: Implement frontend keyword state, toolbar input, and page reset**

  In `useTaskListQueryStore.ts`, keep the existing store and use trimmed keyword in callers.

  In `useTaskListData.tsx`, read the keyword:

  ```tsx
  const keyword = useTaskListQueryStore((state) => state.keyword)
  const normalizedKeyword = keyword.trim()
  ```

  Include it in list params:

  ```tsx
  ...(normalizedKeyword ? { keyword: normalizedKeyword } : {}),
  ```

  Add an effect:

  ```tsx
  useEffect(() => {
    setSelectedTaskIds([])
    setCurrent(1)
  }, [normalizedKeyword, tagNames])
  ```

  In `TaskListPage.tsx`, pass `keyword` and `onKeywordChange` into `TaskListCards`.

  In `TaskListCards.tsx`, import `Input` and render:

  ```tsx
  <Input.Search
    allowClear
    aria-label="搜索任务名称、URL 名称或 URL"
    placeholder="搜索任务名称 / URL 名称 / URL"
    value={keyword}
    onChange={(event) => onKeywordChange(event.target.value)}
    className={styles.taskSearchInput}
  />
  ```

  Add latest-run summary rendering inside `TaskCard`:

  ```tsx
  function LatestRunSummary({ task }: { task: CrawlTask }) {
    if (!task.last_run_status && !task.last_run_at) return <Typography.Text type="secondary">-</Typography.Text>
    const failed = task.last_run_failed
    const total = task.last_run_total
    const hasFailures = typeof failed === 'number' && failed > 0
    return (
      <Typography.Text type={hasFailures ? 'warning' : 'secondary'} className={styles.taskMetaValue}>
        {typeof failed === 'number' && typeof total === 'number'
          ? `失败 ${failed} / 总 ${total}`
          : task.last_run_status === 'failed' ? '失败' : '已完成'}
      </Typography.Text>
    )
  }
  ```

  Add a card row labeled `上次运行`.

- [ ] **Step 10: Run focused frontend crawler task tests**

  Run: `cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx`

  Expected: PASS.

- [ ] **Step 11: Commit Task 1**

  ```bash
  git add backend/app/repositories/crawl_task.py backend/app/schemas/crawl_task.py backend/app/modules/crawler/tasks/serializers.py backend/app/modules/crawler/tasks/service.py backend/tests/test_crawler_task_list_search.py frontend/src/api/crawler/crawlTask/types.ts frontend/src/pages/crawler/tasks/useTaskListQueryStore.ts frontend/src/pages/crawler/tasks/hooks/useTaskListData.tsx frontend/src/pages/crawler/tasks/components/TaskListCards.tsx frontend/src/pages/crawler/tasks/TaskListPage.tsx frontend/src/pages/crawler/tasks/TaskPages.module.less frontend/src/pages/crawler/tasks/__tests__/task-list-query.test.tsx frontend/src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx
  git commit -m "feat: add crawler task search summaries"
  ```

---

### Task 2: Movie List Filter Page Reset

**Files:**
- Modify: `frontend/src/pages/content/movies/hooks/useMovieList.ts`
- Test: `frontend/src/pages/content/movies/__tests__/movie-list-query.test.tsx`

**Interfaces:**
- Consumes: `filterParams: MovieFilterParams | undefined` passed into `useMovieList`.
- Produces: filter changes reset `page` to `DEFAULT_MOVIE_PAGE` and clear `selectedRowKeys`.

- [ ] **Step 1: Write failing hook test for filter-change reset**

  Add this test to `movie-list-query.test.tsx`:

  ```tsx
  it('resets to the first page when effective filters change', async () => {
    vi.mocked(fetchMovies).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, total_pages: 1 } as never)

    const { result, rerender } = renderHook(
      ({ filters }) => useMovieList(filters as never),
      { wrapper, initialProps: { filters: { search: 'abc' } } },
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    act(() => result.current.handlePageChange(3, 20))
    await waitFor(() => expect(result.current.page).toBe(3))

    rerender({ filters: { search: 'xyz' } })

    await waitFor(() => expect(result.current.page).toBe(1))
    expect(result.current.selectedRowKeys).toEqual([])
  })
  ```

- [ ] **Step 2: Run the focused movie hook test and confirm it fails**

  Run: `cd frontend && pnpm test -- src/pages/content/movies/__tests__/movie-list-query.test.tsx`

  Expected: FAIL because `useMovieList` does not reset page on filter param identity change.

- [ ] **Step 3: Implement filter identity tracking**

  In `useMovieList.ts`, import `useRef`:

  ```tsx
  import { useCallback, useEffect, useRef, useState } from "react";
  ```

  Add stable identity near state declarations:

  ```tsx
  const filterKey = JSON.stringify(filterParams ?? {});
  const previousFilterKeyRef = useRef<string | null>(null);
  ```

  Add effect before `loadMovies` effect:

  ```tsx
  useEffect(() => {
    if (!filterParams) {
      previousFilterKeyRef.current = null;
      return;
    }
    if (previousFilterKeyRef.current === null) {
      previousFilterKeyRef.current = filterKey;
      return;
    }
    if (previousFilterKeyRef.current !== filterKey) {
      previousFilterKeyRef.current = filterKey;
      setSelectedRowKeys([]);
      setPage(DEFAULT_MOVIE_PAGE);
    }
  }, [filterKey, filterParams]);
  ```

  Keep existing `search()`, `handleShowSizeChange`, and `handleSortChange` behavior.

- [ ] **Step 4: Run focused movie test**

  Run: `cd frontend && pnpm test -- src/pages/content/movies/__tests__/movie-list-query.test.tsx`

  Expected: PASS.

- [ ] **Step 5: Commit Task 2**

  ```bash
  git add frontend/src/pages/content/movies/hooks/useMovieList.ts frontend/src/pages/content/movies/__tests__/movie-list-query.test.tsx
  git commit -m "fix: reset movie pagination on filter change"
  ```

---

### Task 3: Storage Failed Subtask Retry

**Files:**
- Modify: `backend/app/modules/storage/tasks/service.py`
- Modify: `backend/app/modules/storage/tasks/router.py`
- Modify: `frontend/src/api/storage/storageTasks/index.ts`
- Modify: `frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts`
- Modify: `frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx`
- Test: `backend/tests/test_storage_subtask_retry.py`
- Test: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Produces: `POST /api/storage/tasks/subtasks/{subtask_id}/retry`.
- Produces: `StorageTaskService.retry_subtask(subtask_id: uuid.UUID, user_id: uuid.UUID) -> StorageSubTask`.
- Produces: `retryStorageSubTask(subtaskId: string): Promise<StorageSubTask>`.
- Produces: `StorageSubTaskTable` prop `onRetry?: (subtask: StorageSubTask) => void` and optional `retryingSubtaskId?: string | null`.

- [ ] **Step 1: Write backend failing tests for retry rules**

  Add tests for:

  ```python
  def test_retry_failed_storage_subtask_requeues_failed_subtask_and_parent(db_session, user):
      service = StorageTaskService(db_session, config_service=fake_config_service, runtime=fake_runtime)
      main = StorageMainTask(created_by=user.id, alias="retry", display_name="retry", source="single", storage_mode="single", status="completed", total_count=1, success_count=0, failed_count=1, skipped_count=0)
      db_session.add(main)
      db_session.flush()
      subtask = StorageSubTask(main_task_id=main.id, movie_id=uuid.uuid4(), movie_code="AAA-001", movie_title="Movie", status="failed", step="waiting_download", error_message="not found", magnet_attempts=[{"id": "old"}], current_magnet_url="magnet:?xt=old", renamed_files=[{"old": 1}], moved_files=[{"old": 1}], skipped_files=[{"old": 1}], result={"failed": True})
      db_session.add(subtask)
      db_session.commit()

      retried = service.retry_subtask(subtask.id, user.id)

      assert retried.status == "queued"
      assert retried.step == "prepare"
      assert retried.error_message is None
      assert retried.magnet_attempts == []
      assert retried.current_magnet_url == ""
      assert retried.renamed_files == []
      assert retried.moved_files == []
      assert retried.skipped_files == []
      assert retried.result == {}
      assert retried.main_task.status == "queued"
      assert fake_runtime.enqueued == [str(main.id)]
  ```

  Add rejection tests:

  ```python
  def test_retry_storage_subtask_rejects_non_failed_subtask(...):
      with pytest.raises(ValueError, match="只能重试失败的存储子任务"):
          service.retry_subtask(completed_subtask.id, user.id)

  def test_retry_storage_subtask_rejects_active_parent(...):
      main.status = "running"
      with pytest.raises(ValueError, match="运行中的存储任务不能重试子任务"):
          service.retry_subtask(failed_subtask.id, user.id)

  def test_retry_storage_subtask_rejects_other_user(...):
      with pytest.raises(LookupError, match="存储子任务不存在"):
          service.retry_subtask(failed_subtask.id, other_user.id)
  ```

- [ ] **Step 2: Run backend retry tests and confirm they fail**

  Run: `cd backend && python -m pytest tests/test_storage_subtask_retry.py -v`

  Expected: FAIL because the service method and route do not exist.

- [ ] **Step 3: Implement storage subtask retry service**

  In `StorageTaskService`, add:

  ```python
  def retry_subtask(self, subtask_id: uuid.UUID, user_id: uuid.UUID) -> StorageSubTask:
      subtask = self.repository.get_subtask(subtask_id)
      if subtask is None or subtask.main_task is None or subtask.main_task.created_by != user_id:
          raise LookupError("存储子任务不存在")
      main_task = subtask.main_task
      if main_task.status in {"queued", "running", "stopping"}:
          raise ValueError("运行中的存储任务不能重试子任务")
      if subtask.status != "failed":
          raise ValueError("只能重试失败的存储子任务")

      subtask.status = "queued"
      subtask.step = "prepare"
      subtask.error_message = None
      subtask.started_at = None
      subtask.finished_at = None
      subtask.magnet_attempts = []
      subtask.current_magnet_id = None
      subtask.current_magnet_url = ""
      subtask.renamed_files = []
      subtask.moved_files = []
      subtask.skipped_files = []
      subtask.result = {}
      main_task.status = "queued"
      main_task.started_at = None
      main_task.finished_at = None
      main_task.error_message = None
      self.repository.recompute_counts(main_task)

      if self.runtime is not None:
          self.runtime.clear_stop(str(main_task.id))
          self.runtime.enqueue_main_task(str(main_task.id))
          ensure_storage_worker_started(
              self.runtime,
              self.config_service.provider_factory,
              self.config_service,
          )
      self.db.commit()
      self.db.refresh(subtask)

      from backend.app.modules.storage.tasks.events import publish_storage_main_updated, publish_storage_sub_updated
      publish_storage_main_updated(main_task)
      publish_storage_sub_updated(str(main_task.created_by), subtask)
      return subtask
  ```

  Confirm `StorageSubTask.main_task` relationship name from `backend/app/models/storage_task.py` and adjust if needed.

- [ ] **Step 4: Add retry route**

  In `router.py`, before `/{main_task_id}` routes:

  ```python
  @router.post("/subtasks/{subtask_id}/retry")
  def retry_storage_subtask(subtask_id: UUID, current_user: CurrentUser, service=Depends(get_storage_task_service)):
      try:
          subtask = service.retry_subtask(subtask_id, current_user.id)
          return success(data=service.to_subtask_response(subtask))
      except LookupError as exc:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
      except ValueError as exc:
          raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
  ```

- [ ] **Step 5: Run backend retry tests**

  Run: `cd backend && python -m pytest tests/test_storage_subtask_retry.py -v`

  Expected: PASS.

- [ ] **Step 6: Write frontend failing test for subtask retry action**

  In `storage-task-pages.test.tsx`, mock `retryStorageSubTask`. Make `listStorageSubTasks` return one failed row and one completed row. Assert only one retry button appears and calls the API:

  ```tsx
  import { retryStorageSubTask } from '@/api/storage/storageTasks'

  it('shows retry only for failed storage subtasks and retries that subtask', async () => {
    vi.mocked(listStorageSubTasks).mockResolvedValue({
      rows: [
        { id: 'sub-failed', main_task_id: 'task-detail-1', movie_id: 'movie-1', movie_code: 'AAA-001', movie_title: 'A', status: 'failed', step: 'waiting_download' },
        { id: 'sub-ok', main_task_id: 'task-detail-1', movie_id: 'movie-2', movie_code: 'BBB-002', movie_title: 'B', status: 'completed', step: 'done' },
      ],
      total: 2,
    } as never)
    vi.mocked(retryStorageSubTask).mockResolvedValue({ id: 'sub-failed', status: 'queued' } as never)

    render(<StorageTaskDetailPage />)

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    const retryButtons = screen.getAllByRole('button', { name: /重试/ })
    expect(retryButtons).toHaveLength(1)
    fireEvent.click(retryButtons[0])

    await waitFor(() => expect(retryStorageSubTask).toHaveBeenCalledWith('sub-failed'))
  })
  ```

- [ ] **Step 7: Run frontend storage test and confirm it fails**

  Run: `cd frontend && pnpm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

  Expected: FAIL because no retry API wrapper or table action exists.

- [ ] **Step 8: Implement frontend retry API and detail handler**

  In `frontend/src/api/storage/storageTasks/index.ts`:

  ```tsx
  export function retryStorageSubTask(subtaskId: string): Promise<StorageSubTask> {
    return request.post<StorageSubTask>(`${BASE_URL}/subtasks/${subtaskId}/retry`)
  }
  ```

  In `useStorageTaskDetail.ts`, import wrapper, expand loading type:

  ```tsx
  const [retryingSubtaskId, setRetryingSubtaskId] = useState<string | null>(null)
  const handleRetrySubtask = useCallback(async (subtask: StorageSubTask) => {
    setRetryingSubtaskId(subtask.id)
    try {
      await retryStorageSubTask(subtask.id)
      void fetchTask()
      void fetchSubtasks()
    } finally {
      setRetryingSubtaskId(null)
    }
  }, [fetchTask, fetchSubtasks])
  ```

  Return `handleRetrySubtask` and `retryingSubtaskId`.

- [ ] **Step 9: Implement subtask table retry action**

  In `StorageSubTaskTable.tsx`, import `ReloadOutlined` and `ResponsiveActions`. Add props:

  ```tsx
  onRetry?: (subtask: StorageSubTask) => void
  retryingSubtaskId?: string | null
  ```

  Render actions:

  ```tsx
  const actions: ResponsiveAction[] = [
    {
      key: 'detail',
      label: '详情',
      onClick: () => void navigate({ to: `/storage/tasks/subtasks/${record.id}` }),
    },
    ...(record.status === 'failed' && onRetry
      ? [{
          key: 'retry',
          label: '重试',
          icon: <ReloadOutlined />,
          loading: retryingSubtaskId === record.id,
          onClick: () => void onRetry(record),
        }]
      : []),
  ]
  ```

  Pass handler from `StorageTaskDetailPage.tsx`.

- [ ] **Step 10: Run focused storage retry frontend test**

  Run: `cd frontend && pnpm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

  Expected: PASS.

- [ ] **Step 11: Commit Task 3**

  ```bash
  git add backend/app/modules/storage/tasks/service.py backend/app/modules/storage/tasks/router.py backend/tests/test_storage_subtask_retry.py frontend/src/api/storage/storageTasks/index.ts frontend/src/pages/storage/tasks/hooks/useStorageTaskDetail.ts frontend/src/pages/storage/tasks/components/StorageSubTaskTable.tsx frontend/src/pages/storage/tasks/StorageTaskDetailPage.tsx frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
  git commit -m "feat: retry failed storage subtasks"
  ```

---

### Task 4: Storage Progress Styling And Final Verification

**Files:**
- Modify: `frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx`
- Modify: `frontend/src/pages/storage/tasks/StorageTasks.module.less`
- Test: `frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

**Interfaces:**
- Produces: `getProgressStatus(task: StorageMainTask): "exception" | undefined`.
- Produces: partial failures are visible in the progress meta without making the whole bar exception unless the main task is truly failed with no successful/skipped work.

- [ ] **Step 1: Write failing test for partial-failure progress**

  In `storage-task-pages.test.tsx`, add a test that renders a completed row with `success_count: 26`, `failed_count: 1`, `total_count: 27` and asserts it does not render an Ant Design exception progress class. Use DOM class check if text-level assertion is insufficient:

  ```tsx
  it('does not mark mixed completed storage progress as exception', async () => {
    vi.mocked(listStorageMainTasks).mockResolvedValue({
      rows: [{
        id: 'task-mixed-1',
        alias: '云存储_部分失败',
        display_name: '云存储_部分失败',
        source: 'batch',
        storage_mode: 'single',
        status: 'completed',
        total_count: 27,
        success_count: 26,
        failed_count: 1,
        skipped_count: 0,
        created_at: '2026-09-07T00:00:00Z',
      }],
      page: 1,
      size: 20,
      has_more: false,
    } as never)

    render(<StorageTaskListPage />, { wrapper })

    expect(await screen.findByText('云存储_部分失败')).toBeInTheDocument()
    expect(document.querySelector('.ant-progress-status-exception')).not.toBeInTheDocument()
    expect(screen.getByText('失败 1')).toBeInTheDocument()
  })
  ```

- [ ] **Step 2: Run storage page test and confirm it fails**

  Run: `cd frontend && pnpm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

  Expected: FAIL because `failed_count > 0` currently sets progress `status="exception"`.

- [ ] **Step 3: Implement progress status helper**

  In `StorageMainTaskTable.tsx`:

  ```tsx
  function getProgressStatus(task: StorageMainTask) {
    const hasAnySuccess = task.success_count + task.skipped_count > 0
    if (task.status === 'failed' && !hasAnySuccess) return 'exception' as const
    return undefined
  }
  ```

  Use it:

  ```tsx
  <Progress percent={getProgressPercent(record)} size="small" status={getProgressStatus(record)} />
  ```

  Render failed meta with a warning class:

  ```tsx
  <span className={record.failed_count > 0 ? styles.tableProgressFailedMeta : undefined}>
    失败 {record.failed_count}
  </span>
  ```

- [ ] **Step 4: Add minimal warning styling**

  In `StorageTasks.module.less`:

  ```less
  .tableProgressFailedMeta {
    color: #d48806;
    font-weight: 500;
  }
  ```

- [ ] **Step 5: Run focused storage tests**

  Run: `cd frontend && pnpm test -- src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx`

  Expected: PASS.

- [ ] **Step 6: Run focused frontend test suite for all touched UI**

  Run:

  ```bash
  cd frontend && pnpm test -- src/pages/crawler/tasks/__tests__/task-list-query.test.tsx src/pages/crawler/tasks/__tests__/task-list-card-actions.test.tsx src/pages/content/movies/__tests__/movie-list-query.test.tsx src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
  ```

  Expected: PASS.

- [ ] **Step 7: Run frontend build**

  Run: `cd frontend && pnpm build`

  Expected: PASS.

- [ ] **Step 8: Run backend focused tests**

  Run:

  ```bash
  cd backend && python -m pytest tests/test_crawler_task_list_search.py tests/test_storage_subtask_retry.py -v
  ```

  Expected: PASS.

- [ ] **Step 9: Commit Task 4**

  ```bash
  git add frontend/src/pages/storage/tasks/components/StorageMainTaskTable.tsx frontend/src/pages/storage/tasks/StorageTasks.module.less frontend/src/pages/storage/tasks/__tests__/storage-task-pages.test.tsx
  git commit -m "fix: soften storage progress failures"
  ```

- [ ] **Step 10: Final status check**

  Run:

  ```bash
  git status --short
  git log --oneline -5
  ```

  Expected: working tree clean except any user-owned unrelated files; recent commits include the plan and implementation commits.
