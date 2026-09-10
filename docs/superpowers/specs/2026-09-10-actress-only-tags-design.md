# Actress-Only Tags Design

## Summary

Media Forge will remove crawler task tags completely and make tags belong only to actress profiles. Existing task tags will be migrated into actress tags where an actress can be matched to the tagged task; unmatched task-only tags will be discarded because task tags no longer have product meaning.

The final system has one tag dictionary for actresses, one actress-to-tag association table, no task tag UI, and no task tag API. Actress list filtering and actress detail editing use the actress tag dictionary and relationship tables.

## Goals

- Remove task tag concepts from backend models, schemas, APIs, repositories, backup/restore, frontend pages, and tests.
- Replace `actress_profiles.tags` array storage with normalized actress tag tables.
- Preserve user-visible actress tag behavior:
  - Actress list displays tags.
  - Actress list filters by tags.
  - Actress detail edits tags.
  - The tag editor can choose existing tags and type new tags.
- Migrate existing data:
  - Existing `actress_profiles.tags` values become actress tag rows and links.
  - Existing task tags are copied to actresses whose `source_task_ids` contain the tagged task id.
  - Task tags that cannot be associated with any actress are intentionally dropped.
- Keep movie tags and movie magnet tags unchanged.

## Non-Goals

- Do not preserve task tag filtering in the task list.
- Do not keep `/api/crawler/tasks/tags` as a compatibility endpoint.
- Do not add generic content tags that can attach to many entity types.
- Do not change movie tag storage or movie filter behavior.
- Do not add tag color, ordering, groups, or counts.

## Data Model

### New Tables

`actress_tags`

- `id uuid primary key`
- `owner_id uuid not null references users(id)`
- `name varchar(50) not null`
- `created_at timestamp`
- `updated_at timestamp`
- unique constraint: `(owner_id, name)`
- index: `(owner_id, name)`

`actress_tag_links`

- `actress_profile_id uuid not null references actress_profiles(id) on delete cascade`
- `tag_id uuid not null references actress_tags(id) on delete cascade`
- primary key: `(actress_profile_id, tag_id)`
- index: `actress_profile_id`
- index: `tag_id`

### Removed Tables and Columns

- Drop `crawl_task_tag_links`.
- Drop `crawl_task_tags`.
- Drop `actress_profiles.tags`.
- Drop `idx_actress_profiles_tags_gin`.

### ORM Shape

Add `ActressTag` and `actress_tag_links` under the content domain. `ActressProfile.tags` becomes a SQLAlchemy relationship to `list[ActressTag]`, ordered by tag name.

Remove `CrawlTaskTag`, `crawl_task_tag_links`, and `CrawlTask.tags`.

## Migration Rules

The Alembic migration must run in this order:

1. Create `actress_tags`.
2. Create `actress_tag_links`.
3. Copy existing `actress_profiles.tags` array values into `actress_tags` and `actress_tag_links`.
4. Copy existing task tags into matching actress profiles:
   - Find every row from `crawl_task_tag_links`.
   - Join `crawl_task_tags` by `tag_id`.
   - Link that tag to every actress profile where `task_id = ANY(actress_profiles.source_task_ids)`.
   - If no actress matches the task id, ignore that tag link.
5. Drop `idx_actress_profiles_tags_gin`.
6. Drop `actress_profiles.tags`.
7. Drop `crawl_task_tag_links`.
8. Drop `crawl_task_tags`.

The SQL file in `sql/` must mirror the Alembic upgrade path. Downgrade should recreate the old task tag tables and the `actress_profiles.tags` array from normalized actress tags, but it does not need to reconstruct task tag links that were discarded.

## Backend API

### Removed Task Tag API

Remove `GET /api/crawler/tasks/tags`.

Remove `tag_names` from:

- task list query
- task create request
- task update request
- batch task create request
- task serializers
- task repository filters

Task responses no longer include `tags`.

### Actress Tag API

Add `GET /api/content/actresses/tags`.

Response data:

```json
[
  {"id": "uuid", "name": "清楚"}
]
```

This endpoint returns all actress tags for the current user, ordered by name.

### Actress List API

Keep the existing `tags` query parameter as a comma-separated list of tag names. Internally it filters through `actress_tag_links` and `actress_tags`.

The API response keeps `tags: string[]` for actress list and detail rows.

### Actress Tag Update API

Keep `PUT /api/content/actresses/{profile_id}/tags` request shape:

```json
{"tags": ["清楚", "单体"]}
```

Implementation normalizes names, creates missing `actress_tags` rows for the current user, replaces the actress profile's tag links, commits, and returns the serialized profile.

### Actress Fetch From Task

Remove task tag merging from actress profile fetching. Fetching actress information no longer reads task tags or applies task-derived tags.

## Backend Internals

### Normalization

Use the same tag normalization behavior currently used by crawler task tags:

- Trim whitespace.
- Drop empty values.
- Deduplicate by exact normalized name.
- Reject names longer than 50 characters with HTTP 400.

### Ownership

`actress_profiles` currently do not have an owner column. Tag dictionary rows do have `owner_id`, so API operations use the current user for tag creation/listing. Actress tag links attach profile rows to tags owned by the current user.

If multiple users can see the same actress profile, each user can maintain independent tags for that shared profile. Serialization for API requests must only include tags owned by the current user.

## Backup And Restore

Remove export and restore of:

- `data/crawl_task_tags.jsonl`
- `data/crawl_task_tag_links.jsonl`

Add export and restore of:

- `data/actress_tags.jsonl`
- `data/actress_tag_links.jsonl`

Restore must support old archives that contain task tag files by ignoring those files. Restore should not attempt to recreate task tags.

## Frontend

### Task Pages

Remove task tag UI from:

- task list toolbar
- task cards
- task create/edit form
- batch task create drawer

Remove `TaskTagSelect`, task tag options queries, and related frontend API helpers/types.

### Actress Pages

Add frontend API helper:

```ts
getActressTags(): Promise<ActressTag[]>
```

Add query key:

```ts
queryKeys.actresses.tags()
```

Use actress tag options in:

- actress list tag filter
- actress detail tag editor

The detail tag editor remains `mode="tags"` so custom tags can be typed. Options come from the actress tag dictionary.

After saving tags, invalidate:

- actress detail query
- actress list queries
- actress tag dictionary query

## Tests

### Backend

Add or update tests for:

- metadata contains `actress_tags` and `actress_tag_links`, and no longer contains task tag tables.
- actress tag update creates dictionary rows and links.
- actress tag update can reuse existing tag rows.
- actress list filters by normalized tag links.
- actress tag dictionary endpoint returns existing user-owned tags.
- fetch-from-task no longer applies task tags.
- task create/update/list schemas no longer accept or return tags.
- backup export/restore writes and reads actress tag files, and ignores old task tag files.
- migration moves existing `actress_profiles.tags` and task tag links into actress tag links.

### Frontend

Add or update tests for:

- task form has no task tag selector.
- batch task create drawer has no tag selector.
- task list toolbar has no tag filter.
- actress list tag filter offers existing actress tags.
- actress detail tag editor offers existing actress tags and still accepts custom tags.
- saving actress tags invalidates the actress tag dictionary query.

## Rollout

1. Ship migration, backend changes, frontend changes, and tests together.
2. Run Alembic upgrade locally using the current data folder database config.
3. Verify actress tags survived migration in the UI.
4. Verify task pages still create, edit, list, and run tasks without tag fields.

## Risks

- The migration can discard task-only tags that have no associated actress profile. This is intentional under the new product model.
- Shared actress profiles with per-user tag ownership require serializer and query functions to receive `current_user.id`; otherwise tags from different users could leak.
- Backup compatibility changes need focused tests because old archives may still contain `crawl_task_tags` files.

