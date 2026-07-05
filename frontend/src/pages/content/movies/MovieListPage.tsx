import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Button, Modal, Select, Space, Typography, message } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { DEFAULT_MOVIE_PAGE } from './constants'
import BaseListPage from '@/components/BaseListPage'
import { deleteMovies } from '@/api/movie'
import type { FilterItemConfig } from '@/api/movie'
import type { Movie, MovieDeleteMode, MovieFilterConfig } from '@/api/movie/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { MovieStorageUpdatedPayload, RealtimeEvent } from '@/realtime/types'
import FilterConfigDrawer from './components/FilterConfigDrawer'
import MovieDetailDrawer from './components/MovieDetailDrawer'
import MovieFilterBar from './components/MovieFilterBar'
import StoragePushModal from './components/StoragePushModal'
import { createMovieColumns } from './components/MovieTable'
import { useMovieDetail } from './hooks/useMovieDetail'
import { useMovieFilterConfig } from './hooks/useMovieFilterConfig'
import { useMovieFilters } from './hooks/useMovieFilters'
import { useMovieList } from './hooks/useMovieList'
import { useStoragePush } from './hooks/useStoragePush'
import type { MovieFilterState } from './utils/movieFilter'
import styles from './MovieListPage.module.less'

const movieDeleteModeOptions: Array<{ value: MovieDeleteMode; label: string }> = [
  { value: 'database_only', label: '仅删除数据库' },
  { value: 'cloud_only', label: '仅删除云存储' },
  { value: 'database_and_cloud', label: '同步删除数据库和云存储' },
]

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
  const push = useStoragePush(list.reload)

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
    // Reset to page 1 when filter changes - the useEffect in useMovieList will handle the search
    list.setPage(DEFAULT_MOVIE_PAGE)
  }, [detail, filters, list])

  const handleBulkPush = useCallback(() => {
    push.openBatchPush(list.data.items, list.selectedRowKeys)
  }, [push, list.data.items, list.selectedRowKeys])

  const confirmDeleteMovies = useCallback((movies: Movie[]) => {
    if (movies.length === 0) return
    let selectedMode: MovieDeleteMode = 'database_only'
    const title = movies.length === 1 ? `确认删除 ${movies[0].code}` : `确认批量删除 ${movies.length} 部影片`

    Modal.confirm({
      title,
      content: (
        <div>
          <p>请选择删除模式。删除操作不可撤销。</p>
          <div className={styles.deleteModeRow}>
            <Typography.Text className={styles.deleteModeLabel}>删除模式</Typography.Text>
            <Select<MovieDeleteMode>
              aria-label="删除模式"
              defaultValue="database_only"
              options={movieDeleteModeOptions}
              onChange={(value) => {
                selectedMode = value
              }}
              style={{ width: '100%' }}
            />
          </div>
          <Typography.Text type="danger" className={styles.deleteWarning}>
            删除云存储会删除影片对应的番号文件夹，不会只删除单个视频文件。
          </Typography.Text>
        </div>
      ),
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      width: 520,
      onOk: async () => {
        const result = await deleteMovies({
          movie_ids: movies.map((movie) => movie.id),
          mode: selectedMode,
        })
        message.success(`删除成功：数据库 ${result.deleted_movies} 部，云存储 ${result.cloud_deleted_folders.length} 个文件夹`)
        list.setSelectedRowKeys([])
        list.reload()
      },
    })
  }, [list])

  const handleBatchDelete = useCallback(() => {
    const selectedIds = new Set(list.selectedRowKeys.map((key) => String(key)))
    const selectedMovies = list.data.items.filter((movie) => selectedIds.has(movie._id))
    confirmDeleteMovies(selectedMovies)
  }, [confirmDeleteMovies, list.data.items, list.selectedRowKeys])

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

  useEffect(() => {
    connectRealtime()
    const unsubscribe = subscribeRealtime<MovieStorageUpdatedPayload>(
      'movie.storage.updated',
      (event: RealtimeEvent<MovieStorageUpdatedPayload>) => {
        list.updateMovie(event.payload.movie_id, (movie) => ({
          ...movie,
          storage_status: String(event.payload.storage_summary.storage_status || 'not_stored') as Movie['storage_status'],
          storage_summary: {
            ...movie.storage_summary,
            ...event.payload.storage_summary,
          },
        }))
      },
    )
    return unsubscribe
  }, [list.updateMovie])

  const columns = useMemo(
    () => createMovieColumns({ onViewDetail: detail.showDetail, onPush: push.openSinglePush, onDelete: (movie) => confirmDeleteMovies([movie]) }),
    [detail.showDetail, push.openSinglePush, confirmDeleteMovies],
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
        toolbarLeft={(
          <Space>
            {list.selectedRowKeys.length > 0 && (
              <Button type="primary" size="small" onClick={handleBulkPush}>
                批量推送
              </Button>
            )}
            {list.selectedRowKeys.length > 0 && (
              <Button danger size="small" onClick={handleBatchDelete}>
                批量删除
              </Button>
            )}
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={list.syncingStorage}
              onClick={() => void list.syncStorageStatus()}
            >
              同步存储状态
            </Button>
          </Space>
        )}
        onRefresh={listReady ? list.reload : undefined}
        tableProps={{
          onChange: (pagination) => {
            const newPage = pagination.current ?? 1
            const newPageSize = pagination.pageSize ?? 20
            if (newPage !== list.page || newPageSize !== list.pageSize) {
              list.handlePageChange(newPage, newPageSize)
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

      <StoragePushModal
        open={push.modalOpen}
        mode={push.pushMode}
        movies={push.pushMovies}
        selectedRowKeys={push.selectedKeys}
        loading={push.submitting}
        defaultAlias={push.defaultAlias}
        onCancel={push.closeModal}
        onSubmit={push.submitPush}
      />
    </div>
  )
}

export default MovieListPage
