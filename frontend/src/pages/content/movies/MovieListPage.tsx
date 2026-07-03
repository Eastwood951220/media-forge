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
  const filters = useMovieFilters()
  const effectiveParams = useMemo(
    () => (filters.filtersLoading ? undefined : filters.requestParams),
    [filters.filtersLoading, filters.requestParams],
  )
  const list = useMovieList(effectiveParams)
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
          current: list.page,
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
            onConfigClick={() => configHook.setDrawerOpen(true)}
          />
        )}
        onRefresh={list.reload}
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
