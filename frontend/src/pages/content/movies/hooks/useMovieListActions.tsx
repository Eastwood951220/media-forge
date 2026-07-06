import { useCallback } from 'react'
import { Modal, Select, Typography, message } from 'antd'
import { deleteMovies } from '@/api/movie'
import type { Movie, MovieDeleteMode, MovieFilterConfig } from '@/api/movie/types'
import { DEFAULT_MOVIE_PAGE } from '../constants'
import type { useMovieDetail } from './useMovieDetail'
import type { useMovieFilters } from './useMovieFilters'
import type { useMovieList } from './useMovieList'
import type { useStoragePush } from './useStoragePush'
import type { MovieFilterState } from '../utils/movieFilter'
import { parseSortDefault } from '../utils/sort'
import { applyDetailFilterClick } from '../utils/detailFilter'
import styles from '../MovieListPage.module.less'

const movieDeleteModeOptions: Array<{ value: MovieDeleteMode; label: string }> = [
  { value: 'database_only', label: '仅删除数据库' },
  { value: 'cloud_only', label: '仅删除云存储' },
  { value: 'database_and_cloud', label: '同步删除数据库和云存储' },
]

export function useMovieListActions(args: {
  config: MovieFilterConfig | undefined
  detail: ReturnType<typeof useMovieDetail>
  filters: ReturnType<typeof useMovieFilters>
  list: ReturnType<typeof useMovieList>
  push: ReturnType<typeof useStoragePush>
}) {
  const { config, detail, filters, list, push } = args

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

  const handleBulkPush = useCallback(() => {
    push.openBatchPush(list.data.items, list.selectedRowKeys)
  }, [push, list.data.items, list.selectedRowKeys])

  const handleDetailFilterClick = useCallback((field: string, value: string) => {
    applyDetailFilterClick({
      closeDetail: detail.closeDetail,
      field,
      form: filters.form,
      patchForm: filters.patchForm,
      setPage: list.setPage,
      value,
    })
  }, [detail.closeDetail, filters.form, filters.patchForm, list.setPage])

  const handleResetFilters = useCallback(() => {
    filters.resetFilters()
    if (config) {
      const defaults: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(config)) {
        if (key !== 'sortBy' && value?.defaultValue !== undefined) {
          defaults[key] = value.defaultValue
        }
      }
      if (Object.keys(defaults).length > 0) {
        filters.patchForm(defaults as Partial<MovieFilterState>)
      }
    }
    list.resetSort(parseSortDefault(config))
    list.setPage(DEFAULT_MOVIE_PAGE)
  }, [config, filters, list])

  return {
    confirmDeleteMovies,
    handleBatchDelete,
    handleBulkPush,
    handleDetailFilterClick,
    handleResetFilters,
  }
}
