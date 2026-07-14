import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Button, Dropdown, Space } from 'antd'
import { DatabaseOutlined, DownOutlined, SyncOutlined } from '@ant-design/icons'
import { refreshStorageIndex, type StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
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
  const { message } = App.useApp()
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
  const [indexRefreshing, setIndexRefreshing] = useState<StorageIndexRefreshMode | null>(null)
  const [cd2SyncingId, setCd2SyncingId] = useState<string | null>(null)

  const handleRefreshStorageIndex = useCallback(async (mode: StorageIndexRefreshMode) => {
    setIndexRefreshing(mode)
    try {
      await refreshStorageIndex(mode)
      message.success(`${mode === 'full' ? '全量' : '增量'}索引任务启动成功`)
    } catch (error) {
      const text = error instanceof Error ? error.message : '存储索引任务启动失败'
      if (text.includes('正在进行中')) {
        message.warning('存储索引任务正在进行中')
      } else {
        message.error(text.includes('启动失败') ? text : `存储索引任务启动失败：${text}`)
      }
    } finally {
      setIndexRefreshing(null)
    }
  }, [message])

  const handleCd2Sync = useCallback(async (movie: Movie) => {
    setCd2SyncingId(movie._id)
    try {
      const result = await syncMovieStorageStatusFromCd2(movie._id)
      message.success(`CD2同步完成：${result.status === 'stored' ? '已存储' : '未存储'}`)
      list.reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'CD2同步失败')
    } finally {
      setCd2SyncingId(null)
    }
  }, [list.reload, message])

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
    () => createMovieColumns({
      onViewDetail: detail.showDetail,
      onPush: push.openSinglePush,
      onDelete: (movie) => actions.confirmDeleteMovies([movie]),
      onCd2Sync: handleCd2Sync,
      cd2SyncingId,
    }),
    [detail.showDetail, push.openSinglePush, actions.confirmDeleteMovies, handleCd2Sync, cd2SyncingId],
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
            <Dropdown
              menu={{
                items: [
                  { key: 'full', label: '全量索引', icon: <DatabaseOutlined /> },
                  { key: 'incremental', label: '增量索引', icon: <SyncOutlined /> },
                ],
                onClick: ({ key }) => void handleRefreshStorageIndex(key as StorageIndexRefreshMode),
              }}
            >
              <Button size="small" loading={indexRefreshing !== null}>
                存储索引 <DownOutlined />
              </Button>
            </Dropdown>
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={list.syncingStorage}
              onClick={() => void list.syncStorageStatus()}
            >
              索引同步
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
