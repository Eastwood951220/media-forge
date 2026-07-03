import { useCallback, useState } from 'react'
import { App } from 'antd'
import { createBatchStoragePush, createStoragePush } from '@/api/storage/storageTasks'
import type { StorageMode } from '@/api/storage/storageTasks/types'
import type { Movie } from '@/api/movie/types'

type PushMovie = Pick<Movie, '_id' | 'code' | 'source_name'> & {
  storage_locations?: string[]
}

type PushMode = 'single' | 'batch'

export function useStoragePush(onSuccess: () => void) {
  const { message } = App.useApp()
  const [modalOpen, setModalOpen] = useState(false)
  const [pushMode, setPushMode] = useState<PushMode>('single')
  const [pushMovies, setPushMovies] = useState<PushMovie[]>([])
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([])
  const [submitting, setSubmitting] = useState(false)

  const openSinglePush = useCallback((movie: PushMovie) => {
    setPushMode('single')
    setPushMovies([movie])
    setSelectedKeys([movie._id])
    setModalOpen(true)
  }, [])

  const openBatchPush = useCallback((movies: PushMovie[], keys: React.Key[]) => {
    if (keys.length === 0) {
      message.warning('请先选择要推送的影片')
      return
    }
    setPushMode('batch')
    setPushMovies(movies.filter((m) => keys.includes(m._id)))
    setSelectedKeys(keys)
    setModalOpen(true)
  }, [message])

  const submitPush = useCallback(async (values: { alias?: string; storageMode: StorageMode; selectedStorageLocation?: string }) => {
    setSubmitting(true)
    try {
      if (pushMode === 'single') {
        const movie = pushMovies[0]
        if (!movie) return
        await createStoragePush({
          movie_id: movie._id,
          alias: values.alias,
          storage_mode: values.storageMode,
          selected_storage_location: values.selectedStorageLocation,
        })
      } else {
        await createBatchStoragePush({
          movie_ids: pushMovies.map((m) => m._id),
          alias: values.alias,
          storage_mode: values.storageMode,
        })
      }
      message.success('推送任务已创建')
      setModalOpen(false)
      onSuccess()
    } catch (error: unknown) {
      message.error(error instanceof Error ? error.message : '推送失败')
    } finally {
      setSubmitting(false)
    }
  }, [pushMode, pushMovies, message, onSuccess])

  const closeModal = useCallback(() => {
    setModalOpen(false)
  }, [])

  return {
    modalOpen,
    pushMode,
    pushMovies,
    selectedKeys,
    submitting,
    openSinglePush,
    openBatchPush,
    submitPush,
    closeModal,
  }
}
