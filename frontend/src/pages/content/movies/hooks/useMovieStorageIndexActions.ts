import { useCallback, useState } from 'react'
import { App } from 'antd'
import { refreshStorageIndex, type StorageIndexRefreshMode } from '@/api/storage/storageIndex'
import { syncMovieStorageStatusFromCd2 } from '@/api/movie'
import type { Movie } from '@/api/movie/types'

interface UseMovieStorageIndexActionsArgs {
  reload: () => void
}

export function useMovieStorageIndexActions({ reload }: UseMovieStorageIndexActionsArgs) {
  const { message } = App.useApp()
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
      reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'CD2同步失败')
    } finally {
      setCd2SyncingId(null)
    }
  }, [reload, message])

  return {
    indexRefreshing,
    cd2SyncingId,
    handleRefreshStorageIndex,
    handleCd2Sync,
  }
}
