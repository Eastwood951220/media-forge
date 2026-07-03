# Movie List BaseListPage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the movie list to follow the `ruoyi-react` `BaseListPage` usage pattern, remove the filter/column settings entry point, and make the list height adapt to the available page space.

**Architecture:** Add a local `BaseListPage` component modeled on `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/components/BaseListPage`, but intentionally omit the column settings popover and `storageKey` behavior because this movie list must not expose a column settings layer. Convert the movie table component into column helpers so `MovieListPage` owns the list composition: query area, refresh toolbar, pagination, selection, sorting, adaptive table scroll, detail drawer.

**Tech Stack:** React 19, TypeScript 6, Vite 8, Ant Design 6, Vitest 3, React Testing Library.

---

## File Structure

- Create `frontend/src/components/BaseListPage/types.ts`: generic list-page props, excluding column setting props.
- Create `frontend/src/components/BaseListPage/index.module.less`: flex layout and height constraints copied conceptually from `ruoyi-react`, without column setting styles.
- Create `frontend/src/components/BaseListPage/index.tsx`: query card, toolbar, refresh/query-toggle buttons, adaptive `Table.scroll.y`.
- Create `frontend/tests/base-list-page.test.tsx`: tests for query toggle, refresh callback, toolbar rendering, and adaptive vertical scroll.
- Modify `frontend/src/pages/content/movies/components/MovieTable.tsx`: convert from a table-rendering component into movie column factory helpers.
- Modify `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`: remove `onConfigClick`, `SettingOutlined`, and the “配置” button.
- Create `frontend/src/pages/content/movies/MovieListPage.module.less`: full-height page wrapper for `BaseListPage`.
- Modify `frontend/src/pages/content/movies/MovieListPage.tsx`: replace the two local `Card` wrappers and `FilterConfigDrawer` with `BaseListPage`.
- Modify `frontend/tests/movie-list.ui.test.tsx`: update expectations for no settings button, retained detail button, and unchanged search behavior.

## Non-Goals

- Do not add button permission logic.
- Do not migrate `ruoyi-react` column settings. The movie list must not show a column settings popover or drawer.
- Do not expand backend RBAC, menus, or login response contracts.

### Task 1: Add BaseListPage Without Column Settings

**Files:**
- Create: `frontend/src/components/BaseListPage/types.ts`
- Create: `frontend/src/components/BaseListPage/index.module.less`
- Create: `frontend/src/components/BaseListPage/index.tsx`
- Create: `frontend/tests/base-list-page.test.tsx`

- [ ] **Step 1: Write the failing BaseListPage tests**

Create `frontend/tests/base-list-page.test.tsx` with this content:

```tsx
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import BaseListPage from '../src/components/BaseListPage'
import type { ColumnsType } from 'antd/es/table'

type Row = {
  id: number
  name: string
}

const columns: ColumnsType<Row> = [
  { title: '名称', dataIndex: 'name', key: 'name' },
]

describe('BaseListPage', () => {
  it('renders query, toolbar, table data, and refreshes', async () => {
    const onRefresh = vi.fn()

    render(
      <BaseListPage<Row>
        rowKey="id"
        columns={columns}
        dataSource={[{ id: 1, name: '影片A' }]}
        queryNode={<input aria-label="关键词" />}
        toolbarLeft={<button type="button">批量操作</button>}
        onRefresh={onRefresh}
      />,
    )

    expect(screen.getByLabelText('关键词')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '批量操作' })).toBeInTheDocument()
    expect(screen.getByText('影片A')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '刷新列表' }))

    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('toggles the query area and applies adaptive table height', async () => {
    let resizeCallback: ResizeObserverCallback | undefined
    const OriginalResizeObserver = globalThis.ResizeObserver

    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    }

    const { container } = render(
      <BaseListPage<Row>
        rowKey="id"
        columns={columns}
        dataSource={[{ id: 1, name: '影片A' }]}
        queryNode={<input aria-label="关键词" />}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: '隐藏搜索' }))
    expect(screen.queryByLabelText('关键词')).not.toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '显示搜索' }))
    expect(screen.getByLabelText('关键词')).toBeVisible()

    act(() => {
      resizeCallback?.([
        { contentRect: { height: 520 } as DOMRectReadOnly } as ResizeObserverEntry,
      ], {} as ResizeObserver)
    })

    const tableBody = container.querySelector('.ant-table-body') as HTMLElement | null
    expect(tableBody?.style.maxHeight).toBe('400px')

    globalThis.ResizeObserver = OriginalResizeObserver
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd frontend && npm test -- --run tests/base-list-page.test.tsx
```

Expected: FAIL with module resolution error for `../src/components/BaseListPage`.

- [ ] **Step 3: Implement BaseListPage types**

Create `frontend/src/components/BaseListPage/types.ts`:

```ts
import type { ColumnsType, TablePaginationConfig, TableProps } from 'antd/es/table'
import type { ReactNode } from 'react'

export interface BaseListPageProps<T extends object> {
  rowKey: TableProps<T>['rowKey']
  columns: ColumnsType<T>
  dataSource: T[]
  loading?: boolean
  pagination?: false | TablePaginationConfig
  rowSelection?: TableProps<T>['rowSelection']
  queryNode?: ReactNode
  toolbarLeft?: ReactNode
  tableProps?: Omit<TableProps<T>, 'rowKey' | 'columns' | 'dataSource' | 'loading' | 'pagination' | 'rowSelection' | 'expandable'>
  expandable?: TableProps<T>['expandable']
  onRefresh?: () => void
  queryVisibleDefault?: boolean
}
```

- [ ] **Step 4: Implement BaseListPage styles**

Create `frontend/src/components/BaseListPage/index.module.less`:

```less
.baseListPage {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.queryCard {
  flex-shrink: 0;
}

.hidden {
  display: none;
}

.tableCard {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  :global(.ant-card-body) {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 16px;
  }
}

.toolbar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.toolbarLeft,
.toolbarRight {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tableWrapper {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
```

- [ ] **Step 5: Implement BaseListPage component**

Create `frontend/src/components/BaseListPage/index.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Table, Tooltip } from 'antd'
import { RedoOutlined, SearchOutlined } from '@ant-design/icons'
import type { BaseListPageProps } from './types'
import styles from './index.module.less'

const TABLE_SCROLL_OFFSET = 120
const MIN_TABLE_SCROLL_Y = 160

function useElementHeight<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [height, setHeight] = useState(0)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return

      const nextHeight = Math.round(entry.contentRect.height)
      setHeight((previousHeight) => (previousHeight === nextHeight ? previousHeight : nextHeight))
    })

    resizeObserver.observe(element)
    return () => resizeObserver.disconnect()
  }, [])

  return { ref, height }
}

export default function BaseListPage<T extends object>({
  rowKey,
  columns,
  dataSource,
  loading = false,
  pagination,
  rowSelection,
  queryNode,
  toolbarLeft,
  tableProps,
  expandable,
  onRefresh,
  queryVisibleDefault = true,
}: BaseListPageProps<T>) {
  const [queryVisible, setQueryVisible] = useState(queryVisibleDefault)
  const { ref: tableWrapperRef, height: tableWrapperHeight } = useElementHeight<HTMLDivElement>()

  const tableScrollY = useMemo(() => {
    if (tableWrapperHeight <= 0) return undefined
    return Math.max(tableWrapperHeight - TABLE_SCROLL_OFFSET, MIN_TABLE_SCROLL_Y)
  }, [tableWrapperHeight])

  return (
    <div className={styles.baseListPage}>
      {queryNode && (
        <Card className={`${styles.queryCard} ${queryVisible ? '' : styles.hidden}`} size="small">
          {queryNode}
        </Card>
      )}

      <Card className={styles.tableCard} size="small">
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>{toolbarLeft}</div>
          <div className={styles.toolbarRight}>
            {queryNode && (
              <Tooltip title={queryVisible ? '隐藏搜索' : '显示搜索'}>
                <Button
                  aria-label={queryVisible ? '隐藏搜索' : '显示搜索'}
                  type="text"
                  icon={<SearchOutlined />}
                  onClick={() => setQueryVisible((visible) => !visible)}
                />
              </Tooltip>
            )}
            {onRefresh && (
              <Tooltip title="刷新">
                <Button
                  aria-label="刷新列表"
                  type="text"
                  icon={<RedoOutlined />}
                  onClick={onRefresh}
                />
              </Tooltip>
            )}
          </div>
        </div>

        <div ref={tableWrapperRef} className={styles.tableWrapper}>
          <Table<T>
            rowKey={rowKey}
            columns={columns}
            dataSource={dataSource}
            loading={loading}
            pagination={pagination}
            rowSelection={rowSelection}
            expandable={expandable}
            scroll={{ y: tableScrollY, x: 'max-content' }}
            {...tableProps}
          />
        </div>
      </Card>
    </div>
  )
}
```

- [ ] **Step 6: Run the BaseListPage test to verify it passes**

Run:

```bash
cd frontend && npm test -- --run tests/base-list-page.test.tsx
```

Expected: PASS and `tableBody.style.maxHeight` equals `400px` after the mocked `ResizeObserver` height of `520`.

- [ ] **Step 7: Commit BaseListPage**

Run:

```bash
git add frontend/src/components/BaseListPage frontend/tests/base-list-page.test.tsx
git commit -m "feat: add adaptive base list page"
```

### Task 2: Convert MovieTable To Column Helpers

**Files:**
- Modify: `frontend/src/pages/content/movies/components/MovieTable.tsx`

- [ ] **Step 1: Replace MovieTable with movie column helpers**

Replace `frontend/src/pages/content/movies/components/MovieTable.tsx` with:

```tsx
import { Button, Space, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'

export interface MovieColumnsOptions {
  onViewDetail: (id: string) => void
}

const storageStatusColor: Record<string, string> = {
  pending: 'processing',
  running: 'processing',
  waiting_download: 'processing',
  waiting_retry: 'warning',
  downloading: 'processing',
  moving: 'processing',
  completed: 'success',
  failed: 'error',
  retryable: 'warning',
  missing: 'error',
  skipped: 'default',
}

const storageStatusText: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  waiting_download: '等待下载',
  waiting_retry: '等待重试',
  downloading: '下载中',
  moving: '移动中',
  completed: '已完成',
  failed: '失败',
  retryable: '可重试',
  missing: '文件缺失',
  skipped: '已跳过',
}

function unique(values: string[] | undefined) {
  return [...new Set(values || [])]
}

export function createMovieColumns({ onViewDetail }: MovieColumnsOptions): ColumnsType<Movie> {
  return [
    { title: '番号', dataIndex: 'code', key: 'code', width: 120 },
    { title: '标题', dataIndex: 'source_name', key: 'source_name', ellipsis: true },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      sorter: true,
      render: (value: number | null) => (value != null ? value.toFixed(2) : '-'),
    },
    {
      title: '发行日期',
      dataIndex: 'release_date',
      key: 'release_date',
      width: 160,
      sorter: true,
      defaultSortOrder: 'descend',
    },
    {
      title: '时长',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (value: number) => (value != null ? `${value}分` : '-'),
    },
    {
      title: '演员',
      dataIndex: 'actors',
      key: 'actors',
      width: 180,
      ellipsis: true,
      render: (actors: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(actors).slice(0, 3).map((actor) => <Tag key={actor}>{actor}</Tag>)}
          {unique(actors).length > 3 && <Tag>+{unique(actors).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 240,
      ellipsis: true,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(tags).slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          {unique(tags).length > 3 && <Tag>+{unique(tags).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '存储状态',
      key: 'storage_status',
      width: 100,
      render: (_: unknown, record) => {
        const status = record.storage_summary?.last_status
        if (!status) return <Typography.Text type="secondary">-</Typography.Text>
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 100,
      render: (_: unknown, record) => (
        <Button type="link" size="small" onClick={() => onViewDetail(record._id)}>
          详情
        </Button>
      ),
    },
  ]
}
```

- [ ] **Step 2: Run TypeScript to verify current integration fails**

Run:

```bash
cd frontend && npm run build
```

Expected: FAIL because `MovieListPage.tsx` still imports the default `MovieTable` component that no longer exists.

- [ ] **Step 3: Commit is deferred until MovieListPage uses the new helper**

Do not commit after this task alone. The project intentionally fails until Task 3 wires `createMovieColumns` into `MovieListPage`.

### Task 3: Refactor MovieListPage To BaseListPage And Remove Settings Entry

**Files:**
- Modify: `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`
- Create: `frontend/src/pages/content/movies/MovieListPage.module.less`
- Modify: `frontend/src/pages/content/movies/MovieListPage.tsx`

- [ ] **Step 1: Remove the filter settings prop and button from MovieFilterBar**

In `frontend/src/pages/content/movies/components/MovieFilterBar.tsx`, make these exact edits:

```diff
-import {SearchOutlined, ReloadOutlined, SettingOutlined} from "@ant-design/icons";
+import {SearchOutlined, ReloadOutlined} from "@ant-design/icons";
```

```diff
-    onConfigClick?: () => void;
```

```diff
-export default function MovieFilterBar({filters, sort, filterConfig, onSearch, onReset, onConfigClick}: MovieFilterBarProps) {
+export default function MovieFilterBar({filters, sort, filterConfig, onSearch, onReset}: MovieFilterBarProps) {
```

```diff
-                {onConfigClick && <Button icon={<SettingOutlined/>} onClick={onConfigClick}>配置</Button>}
```

- [ ] **Step 2: Add full-height movie page styles**

Create `frontend/src/pages/content/movies/MovieListPage.module.less`:

```less
.page {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
```

- [ ] **Step 3: Replace MovieListPage with BaseListPage usage**

Replace `frontend/src/pages/content/movies/MovieListPage.tsx` with:

```tsx
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { DEFAULT_MOVIE_PAGE } from './constants'
import BaseListPage from '@/components/BaseListPage'
import type { FilterItemConfig } from '@/api/movie'
import type { Movie, MovieFilterConfig } from '@/api/movie/types'
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
  const filters = useMovieFilters()
  const list = useMovieList(filters.requestParams)
  const detail = useMovieDetail()
  const configHook = useMovieFilterConfig()

  const configSortParsed = useRef(false)
  useEffect(() => {
    if (configSortParsed.current) return
    const sortDefault = parseSortDefault(configHook.config)
    if (sortDefault) {
      list.resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [configHook.config, list.resetSort])

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

  const filterConfig = useMemo(() => configHook.config as Record<string, FilterItemConfig>, [configHook.config])
  const columns = useMemo(
    () => createMovieColumns({ onViewDetail: detail.showDetail }),
    [detail.showDetail],
  )

  return (
    <div className={styles.page}>
      <BaseListPage<Movie>
        rowKey="_id"
        columns={columns}
        dataSource={list.data.items}
        loading={list.loading}
        rowSelection={{
          selectedRowKeys: list.selectedRowKeys,
          onChange: list.setSelectedRowKeys,
        }}
        pagination={{
          current: list.data.page,
          total: list.data.total,
          pageSize: list.pageSize,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (count) => `共 ${count} 条`,
        }}
        queryNode={(
          <MovieFilterBar
            filters={filters}
            sort={{ sortBy: list.sortBy, sortOrder: list.sortOrder, onChange: list.handleSortChange }}
            filterConfig={filterConfig}
            onSearch={list.search}
            onReset={handleResetFilters}
          />
        )}
        onRefresh={list.reload}
        tableProps={{
          onChange: (pagination, _filters, sorter) => {
            const newPage = pagination.current ?? 1
            const newPageSize = pagination.pageSize ?? 20
            if (newPage !== list.data.page || newPageSize !== list.pageSize) {
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
    </div>
  )
}

export default MovieListPage
```

- [ ] **Step 4: Run the build to verify MovieListPage compiles**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS, or fail only on tests not included in build. If build fails on `MovieFilterBarProps`, confirm `onConfigClick` has been fully removed from its interface and call sites.

- [ ] **Step 5: Commit movie list BaseListPage migration**

Run:

```bash
git add frontend/src/pages/content/movies/components/MovieTable.tsx frontend/src/pages/content/movies/components/MovieFilterBar.tsx frontend/src/pages/content/movies/MovieListPage.tsx frontend/src/pages/content/movies/MovieListPage.module.less
git commit -m "refactor: migrate movie list to base list page"
```

### Task 4: Update Movie List UI Tests

**Files:**
- Modify: `frontend/tests/movie-list.ui.test.tsx`

- [ ] **Step 1: Replace movie-list UI tests with BaseListPage expectations**

Replace `frontend/tests/movie-list.ui.test.tsx` with:

```tsx
import { App as AntApp } from 'antd'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../src/pages/content/movies/MovieListPage'
import {
  fetchFilters,
  fetchMovie,
  fetchMovieFilterConfig,
  fetchMovies,
  fetchTaskNames,
  updateMovieFilterConfig,
} from '../src/api/movie'

vi.mock('../src/api/movie', () => ({
  fetchMovies: vi.fn(),
  fetchMovie: vi.fn(),
  fetchTaskNames: vi.fn(),
  fetchFilters: vi.fn(),
  fetchMovieFilterConfig: vi.fn(),
  updateMovieFilterConfig: vi.fn(),
}))

function renderPage() {
  return render(
    <AntApp>
      <MovieListPage />
    </AntApp>,
  )
}

const movie = {
  _id: 'movie-1',
  id: 'movie-1',
  code: 'AAA-001',
  source_url: 'https://javdb.com/v/aaa',
  source_name: '测试电影',
  cover: '',
  release_date: '2026-01-01',
  duration: 120,
  director: '导演A',
  maker: '片商A',
  series: '系列A',
  rating: 4.5,
  actors: ['演员A'],
  tags: ['标签A'],
  source_task_name: '任务A',
  source_task_names: ['任务A'],
  marked: false,
  storage_summary: { last_status: 'completed' },
  raw_detail: {},
  created_at: '2026-07-02T00:00:00',
  updated_at: null,
  magnets: [{
    _id: 'm-1',
    id: 'm-1',
    magnet: 'magnet:?x',
    magnet_url: 'magnet:?x',
    name: '磁力A',
    title: '磁力A',
    size_text: '1.2GB',
    has_chinese_sub: true,
    date: '',
    selected: true,
    dedupe_key: 'abc',
  }],
  selected_magnet_dedupe_key: 'abc',
}

describe('MovieListPage', () => {
  beforeEach(() => {
    vi.mocked(fetchMovies).mockResolvedValue({
      items: [movie],
      total: 1,
      page: 1,
      limit: 20,
      total_pages: 1,
    })
    vi.mocked(fetchMovie).mockResolvedValue(movie)
    vi.mocked(fetchTaskNames).mockResolvedValue([{ name: '任务A' }])
    vi.mocked(fetchFilters).mockImplementation(async (type) => {
      if (type === 'actor') return ['演员A']
      if (type === 'tag') return ['标签A']
      if (type === 'director') return ['导演A']
      if (type === 'maker') return ['片商A']
      if (type === 'series') return ['系列A']
      return []
    })
    vi.mocked(fetchMovieFilterConfig).mockResolvedValue({ _key: 'default', filters: {} })
    vi.mocked(updateMovieFilterConfig).mockResolvedValue({ success: true })
  })

  it('renders filters without settings and opens read-only detail', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索番号、标题...')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /配置/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '隐藏搜索' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '刷新列表' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /详情/ }))

    expect(await screen.findByText('影片详情')).toBeInTheDocument()
    expect(screen.getByText('最佳磁力')).toBeInTheDocument()
    expect(screen.getByText('磁力A')).toBeInTheDocument()
    expect(screen.queryByText('删除')).not.toBeInTheDocument()
    expect(screen.queryByText('推送存储')).not.toBeInTheDocument()
    expect(screen.queryByText('标记')).not.toBeInTheDocument()
  })

  it('does not persist filter drawer settings because the settings entry is removed', async () => {
    renderPage()

    expect(await screen.findByText('AAA-001')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /配置/ })).not.toBeInTheDocument()
    expect(updateMovieFilterConfig).not.toHaveBeenCalled()
  })

  it('sends original filter params when searching', async () => {
    renderPage()

    await userEvent.type(await screen.findByPlaceholderText('搜索番号、标题...'), 'AAA')
    await userEvent.click(screen.getByRole('button', { name: /搜\s*索/ }))

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
})
```

- [ ] **Step 2: Run the movie list UI test**

Run:

```bash
cd frontend && npm test -- --run tests/movie-list.ui.test.tsx
```

Expected: PASS. The old settings persistence test is replaced by a test proving the settings entry is gone and no filter config update is triggered.

- [ ] **Step 3: Run all affected frontend tests**

Run:

```bash
cd frontend && npm test -- --run tests/base-list-page.test.tsx tests/movie-list.ui.test.tsx
```

Expected: PASS for both test files.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS with TypeScript and Vite production build completing successfully.

- [ ] **Step 5: Commit tests**

Run:

```bash
git add frontend/tests/movie-list.ui.test.tsx
git commit -m "test: cover movie list base page behavior"
```

## Final Verification

- [ ] Run targeted tests:

```bash
cd frontend && npm test -- --run tests/base-list-page.test.tsx tests/movie-list.ui.test.tsx
```

Expected: PASS.

- [ ] Run production build:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] Search for removed settings entry points:

```bash
rg -n "onConfigClick|SettingOutlined|FilterConfigDrawer|配置" frontend/src/pages/content/movies frontend/tests/movie-list.ui.test.tsx
```

Expected: no matches for `onConfigClick`, `SettingOutlined`, or `FilterConfigDrawer` in `MovieListPage.tsx` / `MovieFilterBar.tsx`; the only `配置` matches should be test assertions that the button is absent or unrelated backend filter config API names.

## Self-Review

- Spec coverage: The plan maps the referenced `ruoyi-react` `BaseListPage` structure into `media-forge`, omits column settings, makes the table height adaptive, and preserves the existing visible “详情” action.
- Scope: Button permission logic and backend RBAC are excluded per the latest user instruction.
- Type consistency: `BaseListPageProps<T>`, `createMovieColumns`, `MovieFilterBarProps`, and `MovieListPage` call sites use matching TypeScript types.
- Placeholder scan: All tasks name exact files, commands, expected results, and implementation content.
