import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { useRealtimeLifecycle } from '../useRealtimeLifecycle'
import { connectRealtime, disconnectRealtime } from '../eventSourceClient'

vi.mock('../eventSourceClient', () => ({
  connectRealtime: vi.fn(),
  disconnectRealtime: vi.fn(),
}))

describe('useRealtimeLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCrawlerRuntimeStore.getState().reset()
  })

  it('connects once and disconnects plus resets on unmount', () => {
    const { rerender, unmount } = renderHook(() => useRealtimeLifecycle())

    rerender()
    expect(connectRealtime).toHaveBeenCalledTimes(1)

    useCrawlerRuntimeStore.getState().setConnectionStatus('connected')
    unmount()

    expect(disconnectRealtime).toHaveBeenCalledTimes(1)
    expect(useCrawlerRuntimeStore.getState().connectionStatus).toBe('idle')
  })
})