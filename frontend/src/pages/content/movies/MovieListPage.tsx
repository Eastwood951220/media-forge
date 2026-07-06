import { useEffect, useMemo, useRef } from 'react'
import { Button, Space } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import BaseListPage from '@/components/BaseListPage'
import type { FilterItemConfig } from '@/api/movie'
import type { Movie } from '@/api/movie/types'
import FilterConfigDrawer from './components/FilterConfigDrawer'
import MovieDetailDrawer from './components/MovieDetailDrawer'
import MovieFilterBar from './components/MovieFilterBar'
import StoragePushModal from './components/StoragePushModal'
import { createMovieColumns } from './components/MovieTable'
import { useMovieDetail } from './hooks/useMovieDetail'
import { useMovieFilterConfig } from './hooks/useMovieFilterConfig'
import { useMovieFilters } from './hooks/useMovieFilters'
import { useMovieList } from './hooks/useMovieList'
import { useMovieListActions } from './hooks/useMovieListActions'
import { useMovieListRealtime } from './hooks/useMovieListRealtime'
import { useMovieUrlDetail } from './hooks/useMovieUrlDetail'
import { useStoragePush } from './hooks/useStoragePush'
import { parseSortDefault } from './utils/sort'
import styles from './MovieListPage.module.less'

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

  const actions = useMovieListActions({
    config: configHook.config,
    detail,
    filters,
    list,
    push,
  })

  // Apply sort default from config on first load
  const configSortParsed = useRef(false)
  useEffect(() => {
    if (!configHook.loaded || configSortParsed.current) return
    const sortDefault = parseSortDefault(configHook.config)
    if (sortDefault) {
      list.resetSort(sortDefault)
      configSortParsed.current = true
    }
  }, [configHook.loaded, configHook.config, list.resetSort])

  useMovieUrlDetail(detail.showDetail)
  useMovieListRealtime(list.updateMovie)

  const columns = useMemo(
    () => createMovieColumns({ onViewDetail: detail.showDetail, onPush: push.openSinglePush, onDelete: (movie) => actions.confirmDeleteMovies([movie]) }),
    [detail.showDetail, push.openSinglePush, actions.confirmDeleteMovies],
  )

  const queryNode = configHook.loaded ? (
    <MovieFilterBar
      filters={filters}
      sort={{ sortBy: list.sortBy, sortOrder: list.sortOrder, onChange: list.handleSortChange }}
      filterConfig={filterConfig}
      onSearch={list.search}
      onReset={actions.handleResetFilters}
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
              <Button type="primary" size="small" onClick={actions.handleBulkPush}>
                批量推送
              </Button>
            )}
            {list.selectedRowKeys.length > 0 && (
              <Button danger size="small" onClick={actions.handleBatchDelete}>
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
        onFilterClick={actions.handleDetailFilterClick}
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
