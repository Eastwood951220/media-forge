import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Card } from 'antd'
import { DEFAULT_MOVIE_PAGE } from './constants'
import type { FilterItemConfig } from '@/api/movie'
import type { MovieFilterConfig } from '@/api/movie/types'
import MovieDetailDrawer from './components/MovieDetailDrawer'
import FilterConfigDrawer from './components/FilterConfigDrawer'
import MovieFilterBar from './components/MovieFilterBar'
import MovieTable from './components/MovieTable'
import { useMovieDetail } from './hooks/useMovieDetail'
import { useMovieFilterConfig } from './hooks/useMovieFilterConfig'
import { useMovieFilters } from './hooks/useMovieFilters'
import { useMovieList } from './hooks/useMovieList'
import type { MovieFilterState } from './utils/movieFilter'

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
  }, [])

  const filterConfig = useMemo(() => configHook.config as Record<string, FilterItemConfig>, [configHook.config])

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <MovieFilterBar
          filters={filters}
          sort={{ sortBy: list.sortBy, sortOrder: list.sortOrder, onChange: list.handleSortChange }}
          filterConfig={filterConfig}
          onSearch={list.search}
          onReset={handleResetFilters}
          onConfigClick={() => configHook.setDrawerOpen(true)}
        />
      </Card>

      <Card size="medium">
        <MovieTable
          data={list.data.items}
          total={list.data.total}
          page={list.data.page}
          pageSize={list.pageSize}
          loading={list.loading}
          selectedRowKeys={list.selectedRowKeys}
          onSelectionChange={list.setSelectedRowKeys}
          onPageChange={list.handlePageChange}
          onShowSizeChange={list.handleShowSizeChange}
          onSortChange={list.handleSortChange}
          onViewDetail={detail.showDetail}
        />
      </Card>

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
