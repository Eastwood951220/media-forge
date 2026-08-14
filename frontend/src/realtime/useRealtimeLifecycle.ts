import { useEffect } from 'react'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { connectRealtime, disconnectRealtime } from './eventSourceClient'

export function useRealtimeLifecycle(): void {
  useEffect(() => {
    connectRealtime()

    return () => {
      disconnectRealtime()
      useCrawlerRuntimeStore.getState().reset()
    }
  }, [])
}