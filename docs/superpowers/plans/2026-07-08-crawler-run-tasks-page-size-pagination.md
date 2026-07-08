# Crawler Run Tasks: page/size Pagination

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the run detail tasks list API from `skip`/`limit` query params to `page`/`size`, keeping SQL-level pagination.

**Architecture:** Backend endpoint changes from `skip=0&limit=50` to `page=1&size=50`. The SQL offset is computed as `(page - 1) * size`. Frontend API layer and hook update param names accordingly. No change to pagination logic or response format.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, Vitest

## Global Constraints

- Keep SQL-level pagination (offset/limit in query) — do NOT fetch all rows and slice in Python
- Response format stays `{ code, msg, rows, total }` unchanged
- Frontend Ant Design Table pagination already uses `current`/`pageSize` — no UI change needed

---

### Task 1: Backend — change endpoint params from skip/limit to page/size

**Files:**
- Modify: `backend/app/modules/crawler/runs/router.py:63-90`
- Test: `backend/tests/test_crawler_runs_api.py`

**Interfaces:**
- Produces: `GET /{run_id}/tasks?page=1&size=50&status=&keyword=` — `page` is 1-based, `size` defaults to 50, max 200

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crawler_runs_api.py — add test for page/size params

def test_list_run_tasks_accepts_page_and_size(client, auth_headers, seeded_run_with_details):
    """page/size params return correct slice."""
    run_id = seeded_run_with_details
    # page=1, size=1 → first item
    resp = client.get(f"/api/crawler/runs/{run_id}/tasks?page=1&size=1", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 1
    assert body["total"] > 1

    # page=2, size=1 → second item
    resp2 = client.get(f"/api/crawler/runs/{run_id}/tasks?page=2&size=1", headers=auth_headers)
    body2 = resp2.json()
    assert len(body2["rows"]) == 1
    assert body2["rows"][0]["id"] != body["rows"][0]["id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crawler_runs_api.py::test_list_run_tasks_accepts_page_and_size -v`
Expected: FAIL — `page` and `size` are not recognized query params

- [ ] **Step 3: Implement the change**

```python
# backend/app/modules/crawler/runs/router.py — replace list_run_tasks

@router.get("/{run_id}/tasks")
def list_run_tasks(
    run_id: uuid.UUID,
    _current_user: CurrentUser,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description="Page number, 1-based"),
    size: int = Query(default=50, ge=1, le=200, description="Page size"),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = Query(default=None, max_length=200),
) -> dict:
    run = db.get(CrawlRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    query = db.query(CrawlRunDetailTask).filter(CrawlRunDetailTask.run_id == run_id)
    if status_filter is not None:
        query = query.filter(CrawlRunDetailTask.status == status_filter)
    if keyword:
        query = query.filter(
            CrawlRunDetailTask.code.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_name.ilike(f"%{keyword}%")
            | CrawlRunDetailTask.source_url_name.ilike(f"%{keyword}%")
        )
    total = query.count()
    offset = (page - 1) * size
    rows = query.order_by(CrawlRunDetailTask.created_at.asc()).offset(offset).limit(size).all()
    return paginated(
        rows=[CrawlRunDetailTaskRead.model_validate(r).model_dump(mode="json") for r in rows],
        total=total,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_crawler_runs_api.py -v -k "task"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/crawler/runs/router.py backend/tests/test_crawler_runs_api.py
git commit -m "refactor: change run tasks endpoint from skip/limit to page/size"
```

---

### Task 2: Frontend — update API layer and hook to use page/size

**Files:**
- Modify: `frontend/src/api/crawlerRun/index.ts:31-41`
- Modify: `frontend/src/pages/crawler/runs/hooks/useRunDetail.ts:42-57`
- Test: `frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx:126-151`

**Interfaces:**
- Consumes: `GET /api/crawler/runs/{runId}/tasks?page=1&size=50&status=&keyword=`
- Produces: same `PaginatedResponse<CrawlRunDetailTask>` shape

- [ ] **Step 1: Write the failing test**

Update existing test expectations in `run-detail-retry.test.tsx`:

```typescript
// frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
// Update the two pagination tests

it('fetches first task page with page and size', async () => {
  render(<RunDetailPage />)
  await screen.findByText('FAIL-001')
  expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
    page: 1,
    size: 50,
    status: undefined,
    keyword: undefined,
  })
})

it('fetches tasks with server-side pagination params', async () => {
  render(<RunDetailPage />)
  await screen.findByText('FAIL-001')
  expect(getCrawlerRunTasks).toHaveBeenCalledWith('run-1', {
    page: 1,
    size: 50,
    status: undefined,
    keyword: undefined,
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`
Expected: FAIL — API called with `skip`/`limit` instead of `page`/`size`

- [ ] **Step 3: Update the API function**

```typescript
// frontend/src/api/crawlerRun/index.ts — update getCrawlerRunTasks

export function getCrawlerRunTasks(
  runId: string,
  params?: {
    page?: number
    size?: number
    status?: string
    keyword?: string
  },
): Promise<PaginatedResponse<CrawlRunDetailTask>> {
  return request.get<PaginatedResponse<CrawlRunDetailTask>>(`${BASE_URL}/${runId}/tasks`, params)
}
```

- [ ] **Step 4: Update the hook**

```typescript
// frontend/src/pages/crawler/runs/hooks/useRunDetail.ts — update fetchTasks

const fetchTasks = useCallback(async () => {
  if (!id) return
  setLoading(true)
  try {
    const data = await getCrawlerRunTasks(id, {
      page: taskPage,
      size: pageSize,
      status: statusFilter,
      keyword: keyword || undefined,
    })
    setTasks(data.rows)
    setTaskTotal(data.total)
  } finally {
    setLoading(false)
  }
}, [id, keyword, pageSize, statusFilter, taskPage])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/crawlerRun/index.ts frontend/src/pages/crawler/runs/hooks/useRunDetail.ts frontend/src/pages/crawler/runs/__tests__/run-detail-retry.test.tsx
git commit -m "refactor: update frontend to use page/size for run tasks pagination"
```
