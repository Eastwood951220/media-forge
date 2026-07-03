# Movie Config-Gated List Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frontend movies page hide configured query controls by default, wait for the filter config API to finish, then load matching query options and the movie list.

**Architecture:** Add explicit `loading` and `loaded` state to the movie filter config hook, gate movie filter option loading behind that state, and gate `useMovieList` by passing `undefined` params until config and filter options are ready. The UI should not render the configured filter bar before config finishes, so hidden/visible/default-order config is applied before the user sees controls or the list API runs.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest 3, React Testing Library.

---

## Scope

Included:
- Frontend movies page only.
- Hide configured query controls until `fetchMovieFilterConfig()` finishes.
- Start filter option APIs only after the config API finishes.
- Start `fetchMovies()` only after config and filter option APIs have finished.
- Preserve existing default sort parsing from filter config.
- Preserve existing manual search, reset, refresh, pagination, and detail drawer behavior.

Excluded:
- Backend filter config API changes.
- Movie table column changes.
- Storage module work.
- New filter fields beyond the existing config-controlled fields.

## Current Behavior

- `MovieListPage` calls `useMovieFilters()` immediately.
- `useMovieFilters()` calls task/filter option APIs immediately on mount.
- `MovieListPage` computes `effectiveParams` from `filters.filtersLoading`, but `filtersLoading` starts as `false`.
- `useMovieList(effectiveParams)` receives params on the first render and calls `fetchMovies()` before filter config finishes.
- `MovieFilterBar` receives `{}` as config before the config API completes, and `{}` means every config-controlled filter is visible by default.

## Desired Behavior

- Before `fetchMovieFilterConfig()` settles:
  - The configured query controls are not rendered.
  - Filter option APIs are not called.
  - `fetchMovies()` is not called.
- After `fetchMovieFilterConfig()` settles:
  - Filter option APIs start.
  - The query bar renders using the loaded config.
  - The movie list API starts only after filter option APIs finish.

## File Structure

- Modify `frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts`: expose `loading` and `loaded` state while still returning a plain config object for existing consumers.
- Modify `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`: accept an `enabled` option, add `optionsLoaded`, and avoid loading options before enabled.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`: call config first, enable options after config load, pass list params only after config and options are ready, and omit `queryNode` before config load.
- Modify `frontend/tests/movie-list.ui.test.tsx`: add tests proving call order and query visibility.

---

### Task 1: Add Config Hook Loading State

**Files:**
- Modify: `frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts`
- Test: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Add a failing test for hidden query controls before config finishes**

In `frontend/tests/movie-list.ui.test.tsx`, add `getTaskDict` to the imports:

```typescript
import { getTaskDict } from '../src/api/crawlTask'
```

Add this mock after the existing movie API mock block:

```typescript
vi.mock('../src/api/crawlTask', () => ({
  getTaskDict: vi.fn(),
}))
```

Add this helper above `describe('MovieListPage', () => {`:

```typescript
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })
  return { promise, resolve, reject }
}
```

Inside the existing `beforeEach`, add this line after the `fetchTaskNames` mock:

```typescript
    vi.mocked(getTaskDict).mockResolvedValue([{ id: 'task-1', name: '任务A' }])
```

Then add this test after the existing `beforeEach` block:

```typescript
  it('hides configured filters and does not call option or list APIs before filter config completes', () => {
    const configRequest = deferred<Awaited<ReturnType<typeof fetchMovieFilterConfig>>>()
    vi.mocked(fetchMovieFilterConfig).mockReturnValue(configRequest.promise)

    renderPage()

    expect(screen.queryByPlaceholderText('筛选演员')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('筛选标签')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /配置/ })).not.toBeInTheDocument()
    expect(getTaskDict).not.toHaveBeenCalled()
    expect(fetchFilters).not.toHaveBeenCalled()
    expect(fetchMovies).not.toHaveBeenCalled()
  })
```

- [ ] **Step 2: Run the new focused test and verify it fails**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx -t "hides configured filters"
```

Expected: FAIL because `筛选演员`, `配置`, option API calls, or `fetchMovies` happen before `fetchMovieFilterConfig()` finishes.

- [ ] **Step 3: Add loading state to `useMovieFilterConfig`**

Replace `frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts` with:

```typescript
import { useCallback, useEffect, useState } from 'react'
import { App } from 'antd'
import { fetchMovieFilterConfig, updateMovieFilterConfig } from '@/api/movie'
import type { MovieFilterConfig, MovieFilterField } from '@/api/movie/types'

export function useMovieFilterConfig() {
  const { message } = App.useApp()
  const [config, setConfig] = useState<MovieFilterConfig>({})
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setLoaded(false)

    fetchMovieFilterConfig()
      .then((result) => {
        if (cancelled) return
        setConfig(result.filters ?? {})
      })
      .catch(() => {
        if (cancelled) return
        setConfig({})
        message.error('加载筛选配置失败')
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
        setLoaded(true)
      })

    return () => {
      cancelled = true
    }
  }, [message])

  const toggle = useCallback(async (key: MovieFilterField, visible: boolean) => {
    const previous = config
    const updated: MovieFilterConfig = {
      ...config,
      [key]: { ...(config[key] ?? {}), visible },
    }
    setConfig(updated)
    try {
      await updateMovieFilterConfig(updated)
    } catch {
      setConfig(previous)
      message.error('保存筛选配置失败')
    }
  }, [config, message])

  return {
    config,
    loading,
    loaded,
    drawerOpen,
    setDrawerOpen,
    toggle,
    setConfig,
  }
}

export type MovieFilterConfigState = ReturnType<typeof useMovieFilterConfig>
```

- [ ] **Step 4: Run the focused test**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx -t "hides configured filters"
```

Expected: still FAIL. This hook now exposes state, but `MovieListPage` has not used it yet.

- [ ] **Step 5: Commit hook state only after Task 2 passes**

Do not commit after this task yet. The hook state is not wired into the page until Task 2.

---

### Task 2: Gate Filter Option Loading Behind Config Completion

**Files:**
- Modify: `frontend/src/pages/content/movies/hooks/useMovieFilters.ts`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`
- Test: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Add a failing test for option and list loading after config**

Append this test to `frontend/tests/movie-list.ui.test.tsx` after the test from Task 1:

```typescript
  it('loads configured filters and movie list after filter config completes', async () => {
    const configRequest = deferred<Awaited<ReturnType<typeof fetchMovieFilterConfig>>>()
    vi.mocked(fetchMovieFilterConfig).mockReturnValue(configRequest.promise)

    renderPage()

    expect(fetchMovies).not.toHaveBeenCalled()
    expect(fetchFilters).not.toHaveBeenCalled()

    configRequest.resolve({
      _key: 'default',
      filters: {
        actors: { visible: true, order: 0 },
        tags: { visible: false, order: 1 },
        sortBy: { visible: true, order: 2, defaultValue: 'rating:-1' },
      },
    })

    expect(await screen.findByPlaceholderText('筛选演员')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('筛选标签')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(getTaskDict).toHaveBeenCalledTimes(1)
      expect(fetchFilters).toHaveBeenCalled()
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 1,
      limit: 20,
      sort_by: 'rating',
      sort_order: -1,
    }))
  })
```

- [ ] **Step 2: Run the new focused test and verify it fails**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx -t "loads configured filters"
```

Expected: FAIL because `useMovieFilters()` and `useMovieList()` are not gated by config completion yet.

- [ ] **Step 3: Replace `useMovieFilters` with an enabled/optionsLoaded version**

Replace `frontend/src/pages/content/movies/hooks/useMovieFilters.ts` with:

```typescript
import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { App } from 'antd'
import { fetchFilters } from '@/api/movie'
import { getTaskDict } from '@/api/crawlTask'
import { MOVIE_FILTER_OPTION_TYPE } from '../constants'
import type { MovieFilterConfig, SelectOption } from '@/api/movie/types'
import { buildMovieFilterParams, type MovieFilterState } from '../utils/movieFilter'

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败'
}

type FilterAction =
  | { type: 'patch'; payload: Partial<MovieFilterState> }
  | { type: 'reset' }

type UseMovieFiltersOptions = {
  enabled?: boolean
  filterConfig?: MovieFilterConfig
}

const INITIAL_FILTER_STATE: MovieFilterState = {
  selectedTask: undefined,
  search: '',
  ratingMin: undefined,
  ratingMax: undefined,
  actorsCountMin: undefined,
  actorsCountMax: undefined,
  selectedActors: [],
  selectedActorsNot: [],
  selectedTags: [],
  selectedTagsNot: [],
  selectedDirectors: [],
  selectedDirectorsNot: [],
  selectedMakers: [],
  selectedMakersNot: [],
  selectedSeries: [],
  selectedSeriesNot: [],
  storageStatus: undefined,
  releaseDateFrom: null,
  releaseDateTo: null,
  createdAtFrom: null,
  createdAtTo: null,
}

function filterReducer(state: MovieFilterState, action: FilterAction): MovieFilterState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.payload }
    case 'reset':
      return { ...INITIAL_FILTER_STATE }
    default:
      return state
  }
}

function toOptions(values: string[]): SelectOption[] {
  return values.map((value) => ({ value, label: value }))
}

function isVisible(config: MovieFilterConfig | undefined, key: string): boolean {
  return config?.[key as keyof MovieFilterConfig]?.visible !== false
}

export function useMovieFilters(options: UseMovieFiltersOptions = {}) {
  const { message } = App.useApp()
  const enabled = options.enabled ?? true
  const filterConfig = options.filterConfig
  const [form, dispatch] = useReducer(filterReducer, INITIAL_FILTER_STATE)
  const [taskOptions, setTaskOptions] = useState<SelectOption[]>([])
  const [actorOptions, setActorOptions] = useState<SelectOption[]>([])
  const [tagOptions, setTagOptions] = useState<SelectOption[]>([])
  const [directorOptions, setDirectorOptions] = useState<SelectOption[]>([])
  const [makerOptions, setMakerOptions] = useState<SelectOption[]>([])
  const [seriesOptions, setSeriesOptions] = useState<SelectOption[]>([])
  const [filtersLoading, setFiltersLoading] = useState(false)
  const [optionsLoaded, setOptionsLoaded] = useState(false)

  const patchForm = useCallback((payload: Partial<MovieFilterState>) => {
    dispatch({ type: 'patch', payload })
  }, [])

  const resetFilters = useCallback(() => {
    dispatch({ type: 'reset' })
  }, [])

  const loadOptions = useCallback(async () => {
    if (!enabled) {
      setOptionsLoaded(false)
      return
    }

    setFiltersLoading(true)
    setOptionsLoaded(false)
    try {
      const shouldLoadActors = isVisible(filterConfig, 'actors') || isVisible(filterConfig, 'actorsNot')
      const shouldLoadTags = isVisible(filterConfig, 'tags') || isVisible(filterConfig, 'tagsNot')
      const shouldLoadDirectors = isVisible(filterConfig, 'director') || isVisible(filterConfig, 'directorNot')
      const shouldLoadMakers = isVisible(filterConfig, 'maker') || isVisible(filterConfig, 'makerNot')
      const shouldLoadSeries = isVisible(filterConfig, 'series') || isVisible(filterConfig, 'seriesNot')

      const [
        tasks,
        actors,
        tags,
        directors,
        makers,
        series,
      ] = await Promise.all([
        getTaskDict(),
        shouldLoadActors ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.ACTOR) : Promise.resolve([]),
        shouldLoadTags ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.TAG) : Promise.resolve([]),
        shouldLoadDirectors ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.DIRECTOR) : Promise.resolve([]),
        shouldLoadMakers ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.MAKER) : Promise.resolve([]),
        shouldLoadSeries ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.SERIES) : Promise.resolve([]),
      ])

      setTaskOptions(tasks.map((task) => ({ value: task.id, label: task.name })))
      setActorOptions(toOptions(actors))
      setTagOptions(toOptions(tags))
      setDirectorOptions(toOptions(directors))
      setMakerOptions(toOptions(makers))
      setSeriesOptions(toOptions(series))
      setOptionsLoaded(true)
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setFiltersLoading(false)
    }
  }, [enabled, filterConfig, message])

  useEffect(() => {
    void loadOptions()
  }, [loadOptions])

  const requestParams = useMemo(() => buildMovieFilterParams(form), [form])

  return {
    form,
    patchForm,
    resetFilters,
    requestParams,
    taskOptions,
    actorOptions,
    tagOptions,
    directorOptions,
    makerOptions,
    seriesOptions,
    filtersLoading,
    optionsLoaded,
  }
}

export type MovieFilters = ReturnType<typeof useMovieFilters>
```

- [ ] **Step 4: Replace `MovieListPage` with config-gated orchestration**

Replace `frontend/src/pages/content/movies/MovieListPage.tsx` with:

```tsx
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { DEFAULT_MOVIE_PAGE } from './constants'
import BaseListPage from '@/components/BaseListPage'
import type { FilterItemConfig } from '@/api/movie'
import type { Movie, MovieFilterConfig } from '@/api/movie/types'
import FilterConfigDrawer from './components/FilterConfigDrawer'
import MovieDetailDrawer from './components/MovieDetailDrawer'
import MovieFilterBar from './components/MovieFilterBar'
import { createMovieColumns } from './components/MovieTable'
import { useMovieDetail } from './hooks/useMovieDetail'
import { useMovieFilterConfig } from './hooks/useMovieFilterConfig'
import { useMovieFilters } from './hooks/useMovieFilters'
import { useMovieList } from './hooks/useMovieList'
import type { MovieFilterState } from './utils/movieFilter'
import styles from './MovieListPage.module.less'

function parseSortDefault(config: MovieFilterConfig | undefined): { sortBy: string; sortOrder: number } | undefined {
  const raw = config?.sortBy?.defaultValue
  if (typeof raw !== 'string' || !raw.includes(':')) return undefined
  const [field, order] = raw.split(':')
  const parsed = Number(order)
  if (!field || (parsed !== 1 && parsed !== -1)) return undefined
  return { sortBy: field, sortOrder: parsed }
}

function MovieListPage() {
  const configHook = useMovieFilterConfig()
  const filterConfig = useMemo(
    () => configHook.config as Record<string, FilterItemConfig>,
    [configHook.config],
  )
  const filters = useMovieFilters({
    enabled: configHook.loaded,
    filterConfig: configHook.config,
  })
  const listReady = configHook.loaded && filters.optionsLoaded
  const effectiveParams = useMemo(
    () => (listReady ? filters.requestParams : undefined),
    [listReady, filters.requestParams],
  )
  const list = useMovieList(effectiveParams)
  const detail = useMovieDetail()

  const configSortParsed = useRef(false)
  useEffect(() => {
    if (!configHook.loaded || configSortParsed.current) return
    const sortDefault = parseSortDefault(configHook.config)
    if (sortDefault) {
      list.resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [configHook.loaded, configHook.config, list.resetSort])

  const handleDetailFilterClick = useCallback((field: string, value: string) => {
    detail.closeDetail()
    const fieldMap: Record<string, string> = {
      director: 'selectedDirectors',
      maker: 'selectedMakers',
      series: 'selectedSeries',
      actors: 'selectedActors',
      tags: 'selectedTags',
    }
    const stateKey = fieldMap[field]
    if (!stateKey) return
    const current = (filters.form[stateKey as keyof typeof filters.form] as string[]) || []
    if (!current.includes(value)) {
      filters.patchForm({ [stateKey]: [...current, value] } as Partial<MovieFilterState>)
    }
    list.search()
  }, [detail, filters, list])

  const handleResetFilters = useCallback(() => {
    filters.resetFilters()
    if (configHook.config) {
      const defaults: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(configHook.config)) {
        if (key !== 'sortBy' && value?.defaultValue !== undefined) {
          defaults[key] = value.defaultValue
        }
      }
      if (Object.keys(defaults).length > 0) {
        filters.patchForm(defaults as Partial<MovieFilterState>)
      }
    }
    list.resetSort(parseSortDefault(configHook.config))
    list.setPage(DEFAULT_MOVIE_PAGE)
  }, [configHook.config, filters, list])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const movieId = params.get('id')
    if (movieId) {
      detail.showDetail(movieId)
      const url = new URL(window.location.href)
      url.searchParams.delete('id')
      window.history.replaceState({}, '', url.toString())
    }
  }, [detail])

  const columns = useMemo(
    () => createMovieColumns({ onViewDetail: detail.showDetail }),
    [detail.showDetail],
  )

  const queryNode = configHook.loaded ? (
    <MovieFilterBar
      filters={filters}
      sort={{ sortBy: list.sortBy, sortOrder: list.sortOrder, onChange: list.handleSortChange }}
      filterConfig={filterConfig}
      onSearch={list.search}
      onReset={handleResetFilters}
      onConfigClick={() => configHook.setDrawerOpen(true)}
    />
  ) : undefined

  return (
    <div className={styles.page}>
      <BaseListPage<Movie>
        rowKey="_id"
        columns={columns}
        dataSource={list.data.items}
        loading={configHook.loading || filters.filtersLoading || list.loading}
        rowSelection={{
          selectedRowKeys: list.selectedRowKeys,
          onChange: list.setSelectedRowKeys,
        }}
        pagination={{
          current: list.page,
          total: list.data.total,
          pageSize: list.pageSize,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (count) => `共 ${count} 条`,
        }}
        queryNode={queryNode}
        onRefresh={listReady ? list.reload : undefined}
        tableProps={{
          onChange: (pagination, _filters, sorter) => {
            const newPage = pagination.current ?? 1
            const newPageSize = pagination.pageSize ?? 20
            if (newPage !== list.page || newPageSize !== list.pageSize) {
              list.handlePageChange(newPage, newPageSize)
            }

            if (!Array.isArray(sorter) && sorter.column) {
              const field = sorter.field as string
              if (sorter.order === 'ascend') list.handleSortChange(field, 1)
              else if (sorter.order === 'descend') list.handleSortChange(field, -1)
              else list.handleSortChange('created_at', -1)
            }
          },
        }}
      />

      <MovieDetailDrawer
        open={detail.open}
        detail={detail.detail}
        onClose={detail.closeDetail}
        onFilterClick={handleDetailFilterClick}
      />

      <FilterConfigDrawer
        open={configHook.drawerOpen}
        onClose={() => configHook.setDrawerOpen(false)}
        config={filterConfig}
        onSave={(cfg) => configHook.setConfig(cfg as typeof configHook.config)}
      />
    </div>
  )
}

export default MovieListPage
```

- [ ] **Step 5: Run the two focused gating tests**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx -t "filter config"
```

Expected: PASS for the two new tests.

- [ ] **Step 6: Commit gated config and options loading**

Run:

```bash
git add frontend/src/pages/content/movies/hooks/useMovieFilterConfig.ts frontend/src/pages/content/movies/hooks/useMovieFilters.ts frontend/src/pages/content/movies/MovieListPage.tsx frontend/tests/movie-list.ui.test.tsx
git commit -m "fix: gate movie list loading on filter config"
```

Expected: commit succeeds.

---

### Task 3: Preserve Existing Movie Page Behaviors

**Files:**
- Modify: `frontend/tests/movie-list.ui.test.tsx`
- Modify only if tests fail: `frontend/src/pages/content/movies/MovieListPage.tsx`

- [ ] **Step 1: Update the existing search test to wait for the gated initial load**

In `frontend/tests/movie-list.ui.test.tsx`, replace the existing test named `sends original filter params when searching` with:

```typescript
  it('sends original filter params when searching after config and options are ready', async () => {
    renderPage()

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenCalledTimes(1)
    })

    await userEvent.type(await screen.findByPlaceholderText('搜索番号、标题...'), 'AAA')
    const searchButtons = screen.getAllByRole('button', { name: /搜\s*索/ })
    await userEvent.click(searchButtons[0])

    await waitFor(() => {
      expect(fetchMovies).toHaveBeenLastCalledWith(expect.objectContaining({
        search: 'AAA',
        page: 1,
        limit: 20,
        sort_by: 'created_at',
        sort_order: -1,
      }))
    })
  })
```

- [ ] **Step 2: Add a regression test for hidden configured fields**

Append this test to `frontend/tests/movie-list.ui.test.tsx`:

```typescript
  it('does not flash config-hidden filters after config loads', async () => {
    vi.mocked(fetchMovieFilterConfig).mockResolvedValue({
      _key: 'default',
      filters: {
        actors: { visible: true, order: 0 },
        tags: { visible: false, order: 1 },
        tagsNot: { visible: false, order: 2 },
      },
    })

    renderPage()

    expect(await screen.findByPlaceholderText('筛选演员')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('筛选标签')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('排除标签')).not.toBeInTheDocument()
  })
```

- [ ] **Step 3: Run the complete movie list UI test file**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS for all tests in `frontend/tests/movie-list.ui.test.tsx`.

- [ ] **Step 4: Fix only actual regressions found by the test**

If the test from Step 3 fails because `fetchMovies` is called twice on first load when `sortBy.defaultValue` is configured, update the sort default effect in `frontend/src/pages/content/movies/MovieListPage.tsx` to set `configSortParsed.current = true` before `list.resetSort(sortDefault)`:

```tsx
  useEffect(() => {
    if (!configHook.loaded || configSortParsed.current) return
    const sortDefault = parseSortDefault(configHook.config)
    if (sortDefault) {
      configSortParsed.current = true
      list.resetSort(sortDefault)
    }
  }, [configHook.loaded, configHook.config, list.resetSort])
```

Run the test again:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit regression test adjustments**

Run:

```bash
git add frontend/tests/movie-list.ui.test.tsx frontend/src/pages/content/movies/MovieListPage.tsx
git commit -m "test: cover movie filter config gating"
```

Expected: commit succeeds.

---

### Task 4: Frontend Verification

**Files:**
- No new files.

- [ ] **Step 1: Run movie-related frontend tests**

Run:

```bash
cd frontend
npm test -- movie-list.ui.test.tsx movie-table.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run broader list/page regression tests**

Run:

```bash
cd frontend
npm test -- base-list-page.test.tsx task-list-query-state.ui.test.tsx route-keepalive.ui.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run the frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS with TypeScript and Vite build output.

- [ ] **Step 4: Manual browser smoke test**

Run:

```bash
cd frontend
npm run dev
```

Expected: Vite prints a local development URL.

Open the movies page and verify:
- The movie table does not request data until `/api/content/movies/filter-config` finishes.
- Config-controlled filters do not show before the config response.
- Hidden fields from filter config never appear after the config response.
- Search, refresh, reset, pagination, and detail drawer still work.

- [ ] **Step 5: Commit verification fixes if any are required**

If verification finds a code fix, make only the smallest required change, rerun the failing command, then commit:

```bash
git add frontend/src/pages/content/movies frontend/tests
git commit -m "fix: stabilize movie config gated loading"
```

Expected: commit succeeds only when a verification fix was necessary.

## Self-Review

- Spec coverage: The plan hides configured query controls before config completion, waits for config completion before loading query option APIs, and waits for options before calling the movie list API.
- Placeholder scan: The plan contains concrete code blocks and exact commands. It does not rely on unspecified implementation steps.
- Type consistency: `useMovieFilterConfig` returns `loading` and `loaded`; `useMovieFilters` returns `optionsLoaded`; `MovieListPage` uses `configHook.loaded && filters.optionsLoaded` as the list gate.
- Scope guard: The plan changes only the frontend movies page, its local hooks, and tests.
