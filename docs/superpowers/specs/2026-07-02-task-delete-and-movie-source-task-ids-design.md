# Task Delete And Movie Source Task IDs Design

## Goal

Add three task deletion modes and switch movie-task association from task names to task IDs.

This feature lets users delete crawler tasks with a clear choice of cleanup depth:

- delete only the task and its crawler run data;
- delete the task plus associated movie records where appropriate;
- reserve a future cloud-storage deletion mode without implementing cloud deletion now.

## Non-Goals

- Do not preserve or migrate old data.
- Do not keep `movies.source_task_names`.
- Do not implement cloud storage deletion in this iteration.
- Do not dynamically resolve movie source task names in the backend movie response.

## Data Model

### `crawl_tasks`

Add:

- `storage_location`: string, required, max 10 characters.

Rules:

- It is set when a task is created.
- It cannot be modified after creation.
- It is intended for future cloud storage path logic.
- It is not used for movie list source-task display.

### `movies`

Replace:

- remove `source_task_names`.

Add:

- `source_task_ids`: required UUID array, default empty array.

Rules:

- Movie-task association is based only on `source_task_ids`.
- New movie persistence writes the current task ID into `source_task_ids`.
- Existing movie persistence appends the current task ID if absent.
- Movie display names are resolved in the frontend using the task dictionary endpoint.

### `movie_magnets`

No schema change.

When a movie is deleted, its magnets continue to be deleted through the existing `Movie.magnets` ORM cascade.

## API Design

### Task Dictionary

Add:

`GET /api/crawler/tasks/dict`

Auth required.

Response data:

```json
[
  { "id": "task-uuid-1", "name": "JavDB VR 女优列表" },
  { "id": "task-uuid-2", "name": "JavDB 无码" }
]
```

Only `id` and `name` are returned. The endpoint is used by:

- movie list task filter dropdown;
- movie list/detail display mapping from `movie.source_task_ids` to task names.

Remove frontend usage of:

`GET /api/content/movies/task-names`

The backend endpoint may be removed during implementation.

### Task Delete

Change:

`DELETE /api/crawler/tasks/{task_id}`

Add query parameter:

- `mode`: one of `task_only`, `task_and_movies`, `task_movies_and_cloud`.

Use query parameter form:

`DELETE /api/crawler/tasks/{task_id}?mode=task_and_movies`

Response data:

```json
{
  "deleted_task": true,
  "deleted_runs": 3,
  "deleted_detail_tasks": 120,
  "updated_movies": 5,
  "deleted_movies": 2,
  "deleted_magnets": 9,
  "cloud_delete": "not_requested"
}
```

For `task_movies_and_cloud`, the backend returns a not-implemented response before mutating data:

```json
{
  "detail": "云存储删除暂未实现"
}
```

Recommended HTTP status: `501 Not Implemented`.

### Movie List

Change movie filtering from:

- `source_task_name`

to:

- `source_task_id`

Movie API rows return:

- `source_task_ids`

Movie API rows do not return:

- `source_task_names`
- backend-resolved `source_tasks`

The frontend maps IDs to task names using `/api/crawler/tasks/dict`.

## Delete Mode Semantics

### `task_only`

Deletes:

- `crawl_tasks`;
- related `crawl_task_urls`;
- task `crawl_runs`;
- related `crawl_run_detail_tasks`.

Does not modify:

- `movies`;
- `movie_magnets`;
- cloud storage.

### `task_and_movies`

Performs all `task_only` cleanup.

Then processes each movie whose `source_task_ids` contains the deleted task ID:

- If `source_task_ids` has more than one ID, remove only this task ID and keep the movie.
- If `source_task_ids` contains only this task ID, delete the movie.
- When the movie is deleted, delete its `movie_magnets` through existing cascade.

Does not delete cloud storage.

### `task_movies_and_cloud`

Reserved for future cloud storage deletion.

Current behavior:

- frontend shows the option as disabled and clearly marked “暂未实现”;
- backend rejects the mode before any mutation.

## Backend Service Boundary

Deletion logic should live outside the router.

Add a focused service module such as:

`backend/app/modules/crawler/tasks/delete_service.py`

Public function:

```python
delete_crawl_task(db, task, mode) -> DeleteTaskResult
```

Responsibilities:

- validate mode;
- reject cloud mode before mutation;
- count affected runs, detail tasks, movies, magnets;
- update or delete associated movies for `task_and_movies`;
- delete task runs;
- delete task;
- commit once;
- rollback on failure.

The router remains responsible for:

- auth;
- ownership check;
- converting service errors to HTTP responses.

## Frontend Design

### Task Create/Edit Form

Add `storage_location` field.

Create mode:

- required;
- max 10 characters;
- when `task.name` changes and the user has not manually edited `storage_location`, auto-fill `storage_location` from the task name truncated to 10 characters;
- manually changing `storage_location` does not change task name;
- after manual edit, later task-name changes do not overwrite `storage_location`.

Edit mode:

- show `storage_location` as disabled/read-only;
- do not submit changes to `storage_location`.

### Task Delete Confirmation

Replace the current plain confirmation content with a custom content block including a delete mode selector.

Modes:

- `task_only`: “仅删除任务与运行记录”
- `task_and_movies`: “删除任务、运行记录与关联电影”
- `task_movies_and_cloud`: “删除任务、电影与云存储（暂未实现）”

Default mode:

- `task_only`

Third mode:

- disabled;
- visible with “暂未实现” copy.

Confirm button:

- remains danger;
- sends selected mode to `deleteCrawlTask(task.id, mode)`.

### Movie List And Detail

Use:

`GET /api/crawler/tasks/dict`

Frontend stores a dictionary:

```ts
Record<string, string>
```

where key is task ID and value is task name.

Movie rows display source task names by mapping `movie.source_task_ids`.

If a task ID is not found in the dictionary, display:

- `未知任务`;
- optionally include a short ID in tooltip or secondary text.

Movie filtering:

- task filter dropdown uses task IDs;
- request param is `source_task_id`.

## Error Handling

- Unknown delete mode returns `400 Bad Request`.
- `task_movies_and_cloud` returns `501 Not Implemented`.
- Missing task or task not owned by current user returns existing `404`.
- If delete service fails after starting work, rollback and return `500`.
- Frontend shows the backend error message in the existing Ant Design message pattern.

## Testing

### Backend

Add tests for:

- `GET /api/crawler/tasks/dict` returns only current user's `{id,name}` pairs.
- Creating a task requires `storage_location`.
- Updating a task cannot change `storage_location`.
- Movie persistence writes `source_task_ids`.
- Existing movie persistence appends a missing task ID.
- Movie list filters by `source_task_id`.
- `task_only` deletes task, urls, runs, and detail tasks, while movies and magnets remain.
- `task_and_movies` removes the task ID from shared movies.
- `task_and_movies` deletes movies and cascades magnets when the deleted task is the only source task ID.
- `task_movies_and_cloud` returns not implemented and mutates nothing.

### Frontend

Add tests for:

- create form requires `storage_location`;
- `storage_location` auto-syncs from task name until manually edited;
- edit form renders `storage_location` disabled;
- delete modal defaults to `task_only`;
- delete modal sends selected mode;
- cloud mode is disabled;
- movie list loads task dict;
- movie list displays task names by mapping `source_task_ids`;
- movie list sends `source_task_id` filter.

## Acceptance Criteria

- New tasks cannot be created without `storage_location`.
- Existing task edit cannot modify `storage_location`.
- Movies store task associations only in `source_task_ids`.
- Movie UI still displays source task names by using the task dictionary.
- Deleting a task with `task_only` removes task and run data only.
- Deleting a task with `task_and_movies` updates or deletes associated movies according to `source_task_ids`.
- Cloud deletion mode is visible as future work but cannot be selected or executed.
