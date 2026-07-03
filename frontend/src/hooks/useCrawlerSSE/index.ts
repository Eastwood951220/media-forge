/**
 * useCrawlerSSE — React hook for consuming crawler real-time events.
 *
 * Uses fetch() + ReadableStream (not native EventSource) to support
 * JWT authentication via query parameters.
 *
 * Features:
 * - Auto-reconnect with exponential backoff (max 5 retries)
 * - Typed event callbacks
 * - Connection status tracking
 * - Automatic cleanup on unmount
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  type CrawlerEvent,
  type SSEConnectionStatus,
  createSSEConnection,
} from '@/api/crawler/sse'
import { getToken } from '@/utils/auth'

// ---- Types ----

export interface UseCrawlerSSEOptions {
  /** Enable/disable the connection (default: true) */
  enabled?: boolean
  /** Callback for each crawler event */
  onEvent?: (event: CrawlerEvent) => void
  /** Callback for run status events specifically */
  onRunStatus?: (event: CrawlerEvent & { type: 'run:status' }) => void
  /** Callback for run progress events specifically */
  onRunProgress?: (event: CrawlerEvent & { type: 'run:progress' }) => void
  /** Callback for task status events specifically */
  onTaskStatus?: (event: CrawlerEvent & { type: 'task:status' }) => void
  /** Maximum reconnection attempts (default: 5) */
  maxRetries?: number
  /** Base reconnect delay in ms (default: 1000, doubles each retry) */
  baseDelay?: number
}

export interface UseCrawlerSSEReturn {
  /** Current connection status */
  status: SSEConnectionStatus
  /** Manually reconnect */
  reconnect: () => void
  /** Manually disconnect */
  disconnect: () => void
}

// ---- Hook ----

const DEFAULT_MAX_RETRIES = 5
const DEFAULT_BASE_DELAY = 1_000

export function useCrawlerSSE(options: UseCrawlerSSEOptions = {}): UseCrawlerSSEReturn {
  const {
    enabled = true,
    onEvent,
    onRunStatus,
    onRunProgress,
    onTaskStatus,
    maxRetries = DEFAULT_MAX_RETRIES,
    baseDelay = DEFAULT_BASE_DELAY,
  } = options

  const [status, setStatus] = useState<SSEConnectionStatus>('disconnected')

  // Use refs for callbacks to avoid reconnecting on callback identity changes
  const onEventRef = useRef(onEvent)
  const onRunStatusRef = useRef(onRunStatus)
  const onRunProgressRef = useRef(onRunProgress)
  const onTaskStatusRef = useRef(onTaskStatus)

  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { onRunStatusRef.current = onRunStatus }, [onRunStatus])
  useEffect(() => { onRunProgressRef.current = onRunProgress }, [onRunProgress])
  useEffect(() => { onTaskStatusRef.current = onTaskStatus }, [onTaskStatus])

  const controllerRef = useRef<AbortController | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enabledRef = useRef(enabled)
  const maxRetriesRef = useRef(maxRetries)
  const baseDelayRef = useRef(baseDelay)

  // Keep refs in sync
  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { maxRetriesRef.current = maxRetries }, [maxRetries])
  useEffect(() => { baseDelayRef.current = baseDelay }, [baseDelay])

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [])

  // Store connect in a ref so handleStatus can reference it without
  // triggering a circular dependency in useCallback.
  const connectRef = useRef<() => void>(() => {})

  const connect = useCallback(() => {
    // Clean up existing connection
    if (controllerRef.current) {
      controllerRef.current.abort()
    }

    const token = getToken()
    if (!token) {
      setStatus('error')
      return
    }

    const handleEvent = (event: CrawlerEvent) => {
      onEventRef.current?.(event)

      switch (event.type) {
        case 'run:status':
          onRunStatusRef.current?.(event)
          break
        case 'run:progress':
          onRunProgressRef.current?.(event)
          break
        case 'task:status':
          onTaskStatusRef.current?.(event)
          break
      }
    }

    const handleStatus = (newStatus: SSEConnectionStatus) => {
      setStatus(newStatus)

      if (newStatus === 'connected') {
        // Reset retry count on successful connection
        retryCountRef.current = 0
      } else if (newStatus === 'disconnected') {
        // Auto-reconnect if not manually disconnected
        if (enabledRef.current && retryCountRef.current < maxRetriesRef.current) {
          const delay = baseDelayRef.current * Math.pow(2, retryCountRef.current)
          retryCountRef.current += 1
          retryTimerRef.current = setTimeout(() => {
            connectRef.current()
          }, delay)
        }
      }
    }

    const handleError = (error: Error) => {
      console.error('[useCrawlerSSE] Connection error:', error.message)
    }

    controllerRef.current = createSSEConnection({
      token,
      onEvent: handleEvent,
      onStatus: handleStatus,
      onError: handleError,
    })
  }, [])

  // Keep the ref in sync with the latest connect callback via effect
  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  const disconnect = useCallback(() => {
    clearRetryTimer()
    if (controllerRef.current) {
      controllerRef.current.abort()
      controllerRef.current = null
    }
    setStatus('disconnected')
    retryCountRef.current = 0
  }, [clearRetryTimer])

  const reconnect = useCallback(() => {
    retryCountRef.current = 0
    disconnect()
    connectRef.current()
  }, [disconnect])

  // Store disconnect in a ref so the effect cleanup can call it
  const disconnectRef = useRef<() => void>(() => {})
  useEffect(() => { disconnectRef.current = disconnect }, [disconnect])

  // Connect/disconnect based on enabled state
  // Schedule state-changing calls on next tick to avoid sync setState in effect body
  useEffect(() => {
    if (!enabled) {
      const timer = setTimeout(() => disconnectRef.current(), 0)
      return () => clearTimeout(timer)
    }

    const timer = setTimeout(() => connectRef.current(), 0)

    return () => {
      clearTimeout(timer)
      // Cleanup on unmount or dependency change — schedule to avoid sync setState
      setTimeout(() => disconnectRef.current(), 0)
    }
  }, [enabled])

  return { status, reconnect, disconnect }
}
