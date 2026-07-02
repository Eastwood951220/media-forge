# Fix Task URL Name And Edit Duplicate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist crawler task URL names during create/edit and allow editing a task without falsely failing on its unchanged URL.

**Architecture:** Fix the backend update path by replacing child URL rows with an in-place merge keyed by URL, so unchanged URLs update their existing `crawl_task_urls` rows instead of deleting and reinserting into the same `(task_id, url)` unique constraint. Fix the frontend form by registering `url_name` in the Ant Design form store and by auto-enriching missing URL names before create/update, matching the original `jav-scrapling` behavior. Add focused backend API tests and frontend UI tests that reproduce the exact payload.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Pytest, React 19, TypeScript, Ant Design, Vitest, React Testing Library.

---

## Debugging Notes

- Reproduced the edit failure with an in-memory TestClient run:
  - `POST /api/crawler/tasks` with `{"name":"巨乳","urls":[{"url":"https://javdb.com/actors/QV49G",...,"url_name":""}]}` returns `201`.
  - `PUT /api/crawler/tasks/{id}` with the same payload returns `400 {"code":400,"msg":"任务 URL 重复","data":null}`.
- Root cause for edit duplicate:
  - `backend/app/repositories/crawl_task.py::replace_urls()` currently does `task.urls.clear()` and then `task.urls.extend(new_rows)`.
  - SQLAlchemy can attempt to insert the new child row before the delete-orphan rows are flushed.
  - The existing row still has the same `task_id` and `url`, so the database raises `uq_crawl_task_urls_task_url`.
- Root cause for missing URL name:
  - Current `TaskFormPage.tsx` only sends `entry.url_name ?? ''`.
  - The original `jav-scrapling` form auto-extracted missing `url_name` values during submit.
  - Current form displays a derived URL name but does not register a hidden `Form.Item name={[index, 'url_name']}` field, so the form contract is fragile even when the user clicks "获取名称".

## File Structure

- Modify: `backend/app/repositories/crawl_task.py`
  - Add `build_url_values()` so create and update share one URL-entry normalization path.
  - Change `replace_urls()` to update existing rows keyed by URL and append only genuinely new rows.
- Modify: `backend/tests/test_crawl_tasks_api.py`
  - Add an API test for editing the exact user payload with the same URL.
  - Add an API test proving `url_name` updates and persists after edit.
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`
  - Register `url_name` as a hidden form field.
  - Add `enrichUrlEntriesWithNames()` and call it before create/update.
  - Keep manual "获取名称" writing to the same form field.
- Modify: `frontend/tests/task-form-restore.ui.test.tsx`
  - Add tests for manual extraction writing `url_name`.
  - Add tests for submit-time auto extraction when `url_name` is empty.

---

### Task 1: Add Backend Regression Tests For Edit URL Replacement

**Files:**
- Modify: `backend/tests/test_crawl_tasks_api.py`

- [ ] **Step 1: Write failing tests**

Append these tests inside `class TestCrawlTasksApi` in `backend/tests/test_crawl_tasks_api.py`:

```python
    def test_update_task_keeps_same_url_without_duplicate_error(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        created_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert created_response.status_code == HTTPStatus.CREATED
        task_id = created_response.json()["data"]["id"]

        update_response = client.put(
            f"/api/crawler/tasks/{task_id}",
            json=payload,
            headers=headers,
        )

        assert update_response.status_code == HTTPStatus.OK
        body = update_response.json()
        assert body["code"] == 200
        assert body["data"]["name"] == "巨乳"
        assert body["data"]["urls"][0]["url"] == "https://javdb.com/actors/QV49G"

    def test_update_task_persists_url_name(
        self,
        client: TestClient,
        admin_user,
    ) -> None:
        headers = auth_headers(client, admin_user)
        payload = exact_user_payload()
        created_response = client.post("/api/crawler/tasks", json=payload, headers=headers)
        assert created_response.status_code == HTTPStatus.CREATED
        task_id = created_response.json()["data"]["id"]

        payload["urls"][0]["url_name"] = "演员 QV49G"
        update_response = client.put(
            f"/api/crawler/tasks/{task_id}",
            json=payload,
            headers=headers,
        )

        assert update_response.status_code == HTTPStatus.OK
        assert update_response.json()["data"]["urls"][0]["url_name"] == "演员 QV49G"

        detail_response = client.get(f"/api/crawler/tasks/{task_id}", headers=headers)
        assert detail_response.status_code == HTTPStatus.OK
        assert detail_response.json()["data"]["urls"][0]["url_name"] == "演员 QV49G"
```

- [ ] **Step 2: Run tests to verify the edit test fails**

Run:

```bash
./.venv/bin/python -m pytest \
  backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_update_task_keeps_same_url_without_duplicate_error \
  backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_update_task_persists_url_name \
  -v
```

Expected before implementation: `test_update_task_keeps_same_url_without_duplicate_error` fails with `400` and `msg == "任务 URL 重复"`.

- [ ] **Step 3: Commit failing tests**

```bash
git add backend/tests/test_crawl_tasks_api.py
git commit -m "test: reproduce crawler task edit url duplicate"
```

---

### Task 2: Fix Backend URL Row Replacement

**Files:**
- Modify: `backend/app/repositories/crawl_task.py`

- [ ] **Step 1: Refactor URL value construction**

In `backend/app/repositories/crawl_task.py`, replace `build_url_rows()` with this shared helper plus the updated row builder:

```python
    def build_url_values(self, entry: TaskUrlEntryCreate, position: int) -> dict:
        source = determine_source(entry.url)
        final_url = build_final_url(
            url=entry.url,
            url_type=entry.url_type,
            has_magnet=entry.has_magnet,
            has_chinese_sub=entry.has_chinese_sub,
            sort_type=entry.sort_type,
            source=source,
        )
        return {
            "position": position,
            "url": entry.url,
            "url_type": entry.url_type,
            "has_magnet": entry.has_magnet,
            "has_chinese_sub": entry.has_chinese_sub,
            "sort_type": entry.sort_type,
            "source": source,
            "final_url": entry.final_url or final_url,
            "url_name": entry.url_name,
        }

    def build_url_rows(self, entries: list[TaskUrlEntryCreate]) -> list[CrawlTaskUrl]:
        return [
            CrawlTaskUrl(**self.build_url_values(entry, position))
            for position, entry in enumerate(entries)
        ]
```

- [ ] **Step 2: Replace delete/reinsert with URL-keyed merge**

Replace `replace_urls()` in `backend/app/repositories/crawl_task.py`:

```python
    def replace_urls(self, task: CrawlTask, urls: list[TaskUrlEntryCreate]) -> None:
        existing_by_url = {row.url: row for row in task.urls}
        next_rows: list[CrawlTaskUrl] = []

        for position, entry in enumerate(urls):
            values = self.build_url_values(entry, position)
            row = existing_by_url.pop(entry.url, None)
            if row is None:
                row = CrawlTaskUrl(**values)
            else:
                for field, value in values.items():
                    setattr(row, field, value)
            next_rows.append(row)

        task.urls = next_rows
```

This keeps an unchanged URL on its existing child row, updates `url_name`, and lets SQLAlchemy delete rows that disappeared from the submitted URL list.

- [ ] **Step 3: Run backend regression tests**

Run:

```bash
./.venv/bin/python -m pytest \
  backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_update_task_keeps_same_url_without_duplicate_error \
  backend/tests/test_crawl_tasks_api.py::TestCrawlTasksApi::test_update_task_persists_url_name \
  -v
```

Expected: PASS.

- [ ] **Step 4: Run full crawler task API tests**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit backend fix**

```bash
git add backend/app/repositories/crawl_task.py
git commit -m "fix: update crawler task urls in place"
```

---

### Task 3: Add Frontend Tests For URL Name Persistence

**Files:**
- Modify: `frontend/tests/task-form-restore.ui.test.tsx`

- [ ] **Step 1: Add a test for manual name extraction**

Append this test inside `describe('TaskFormPage restored crawler task form', ...)`:

```typescript
  it('stores manually extracted url_name in create payload', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '巨乳')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/QV49G')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '获取名称' })).not.toBeDisabled()
    })
    await userEvent.click(screen.getByRole('button', { name: '获取名称' }))

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/QV49G', 'actors')
    })
    await screen.findByDisplayValue('演员 A')

    const submitButton = document.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()
    await userEvent.click(submitButton!)

    await waitFor(() => {
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '巨乳',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/QV49G',
            url_type: 'actors',
            has_magnet: true,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '演员 A',
          },
        ],
      })
    })
  })
```

- [ ] **Step 2: Add a test for submit-time auto extraction**

Append this test in the same `describe` block:

```typescript
  it('auto extracts missing url_name before creating a task', async () => {
    renderForm()

    await userEvent.type(await screen.findByLabelText('任务名称'), '巨乳')
    await userEvent.type(screen.getByLabelText('URL'), 'https://javdb.com/actors/QV49G')

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '获取名称' })).not.toBeDisabled()
    })

    const submitButton = document.querySelector('button[type="submit"]')
    expect(submitButton).toBeTruthy()
    await userEvent.click(submitButton!)

    await waitFor(() => {
      expect(extractTaskName).toHaveBeenCalledWith('https://javdb.com/actors/QV49G', 'actors')
      expect(createCrawlTask).toHaveBeenCalledWith({
        name: '巨乳',
        is_skip: false,
        urls: [
          {
            url: 'https://javdb.com/actors/QV49G',
            url_type: 'actors',
            has_magnet: true,
            has_chinese_sub: false,
            sort_type: 0,
            url_name: '演员 A',
          },
        ],
      })
    })
  })
```

- [ ] **Step 3: Run tests to verify current failures**

Run:

```bash
cd frontend && npm test -- task-form-restore.ui.test.tsx
```

Expected before implementation: at least the submit-time auto extraction test fails because `handleSubmit()` currently maps `url_name: entry.url_name ?? ''` without calling `extractTaskName()`.

- [ ] **Step 4: Commit failing frontend tests**

```bash
git add frontend/tests/task-form-restore.ui.test.tsx
git commit -m "test: cover crawler task url name submission"
```

---

### Task 4: Persist URL Name In Frontend Create And Edit Payloads

**Files:**
- Modify: `frontend/src/pages/crawler/tasks/TaskFormPage.tsx`

- [ ] **Step 1: Register hidden `url_name` field**

In `UrlEntryCard`, after the hidden `url_type` field, add:

```tsx
              <Form.Item name={[index, 'url_name']} hidden>
                <Input />
              </Form.Item>
```

The block should become:

```tsx
              <Form.Item name={[index, 'url_type']} hidden>
                <Input />
              </Form.Item>
              <Form.Item name={[index, 'url_name']} hidden>
                <Input />
              </Form.Item>
```

- [ ] **Step 2: Add submit-time URL-name enrichment helper**

Inside `TaskFormPage`, above `handleSubmit`, add:

```tsx
  const enrichUrlEntriesWithNames = useCallback(
    async (urlEntries: TaskUrlEntry[]): Promise<TaskUrlEntry[]> => {
      const enrichedEntries: TaskUrlEntry[] = []

      for (const entry of urlEntries) {
        let urlName = entry.url_name?.trim() ?? ''

        if (!urlName && entry.url && entry.url_type) {
          try {
            const result = await extractTaskName(entry.url, entry.url_type)
            urlName = result.name?.trim() ?? ''
          } catch {
            urlName = ''
          }
        }

        enrichedEntries.push({
          url: entry.url,
          url_type: entry.url_type,
          has_magnet: entry.has_magnet ?? false,
          has_chinese_sub: entry.has_chinese_sub ?? false,
          sort_type: entry.sort_type ?? 0,
          url_name: urlName,
        })
      }

      return enrichedEntries
    },
    [],
  )
```

- [ ] **Step 3: Use enriched entries in `handleSubmit()`**

Replace the current `payload` construction inside `handleSubmit()`:

```tsx
      const payload: CrawlTaskCreateParams = {
        name: values.name,
        is_skip: values.is_skip ?? false,
        urls: urlEntries.map((entry) => ({
          url: entry.url,
          url_type: entry.url_type,
          has_magnet: entry.has_magnet ?? false,
          has_chinese_sub: entry.has_chinese_sub ?? false,
          sort_type: entry.sort_type ?? 0,
          url_name: entry.url_name ?? '',
        })),
      }
```

with:

```tsx
      const enrichedEntries = await enrichUrlEntriesWithNames(urlEntries)
      form.setFieldsValue({ urls: enrichedEntries })

      const payload: CrawlTaskCreateParams = {
        name: values.name,
        is_skip: values.is_skip ?? false,
        urls: enrichedEntries,
      }
```

- [ ] **Step 4: Keep manual extraction writing the registered field**

Leave the existing callback as the single manual extraction path:

```tsx
                      onNameExtracted={(index, name) => {
                        setUrlEntryValue(index, { url_name: name })
                        if (!form.getFieldValue('name')) form.setFieldsValue({ name })
                      }}
```

With the hidden `url_name` field registered, this value is visible in the form store and included in `values.urls`.

- [ ] **Step 5: Run frontend form tests**

Run:

```bash
cd frontend && npm test -- task-form-restore.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit frontend fix**

```bash
git add frontend/src/pages/crawler/tasks/TaskFormPage.tsx
git commit -m "fix: persist crawler task url names"
```

---

### Task 5: Verify Focused Backend And Frontend Behavior

**Files:**
- No additional files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
./.venv/bin/python -m pytest backend/tests/test_crawl_tasks_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && npm test -- task-form-restore.ui.test.tsx task-url-utils.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with no TypeScript errors.

- [ ] **Step 4: Manually verify the exact edit payload**

After starting the backend and logging in, create and then update the same task with:

```json
{
  "name": "巨乳",
  "is_skip": false,
  "urls": [
    {
      "url": "https://javdb.com/actors/QV49G",
      "url_type": "actors",
      "has_magnet": true,
      "has_chinese_sub": false,
      "sort_type": 0,
      "url_name": "演员 QV49G"
    }
  ]
}
```

Expected update response:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "name": "巨乳",
    "urls": [
      {
        "url": "https://javdb.com/actors/QV49G",
        "url_name": "演员 QV49G"
      }
    ]
  }
}
```

- [ ] **Step 5: Confirm the empty-name frontend path is fixed**

In the browser task form:

1. Enter `https://javdb.com/actors/QV49G`.
2. Do not click `获取名称`.
3. Submit the form.

Expected network payload: `urls[0].url_name` is the extracted name when extraction succeeds, not `""`.

---

## Self-Review

- Spec coverage:
  - Missing `url_name` persistence is covered by manual extraction and submit-time auto extraction tests.
  - The edit API duplicate error is covered by `test_update_task_keeps_same_url_without_duplicate_error`.
  - The exact user URL payload is used in backend tests and manual verification.
- Placeholder scan:
  - No `TBD`, vague validation steps, or "similar to" steps remain.
  - Every implementation step includes concrete code.
- Type consistency:
  - Frontend helper uses existing `TaskUrlEntry`, `CrawlTaskCreateParams`, and `extractTaskName`.
  - Backend helper names are `build_url_values()`, `build_url_rows()`, and `replace_urls()`.
  - Response expectations keep the existing `{code,msg,data}` envelope.
