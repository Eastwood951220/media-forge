/**
 * SSE adapter for crawler real-time events.
 *
 * Provides helpers to connect to the backend SSE stream and parse
 * incoming events into typed CrawlerEvent objects.
 *
 * Uses fetch() + ReadableStream instead of native EventSource to
 * support authentication headers.
 */

import type { CrawlRunStatus, DetailTaskStatus } from '@/api/crawlerRun/types'

// ---- Event types (mirrors backend schemas) ----

export interface RunStatusEvent {
  type: 'run:status'
  timestamp: string
  run_id: string
  status: CrawlRunStatus
  task_name: string
  error?: string | null
}

export interface RunProgressEvent {
  type: 'run:progress'
  timestamp: string
  run_id: string
  total: number
  saved: number
  failed: number
  skipped: number
  save_failed: number
}

export interface RunLogEvent {
  type: 'run:log'
  timestamp: string
  run_id: string
  level: string
  message: string
  context?: Record<string, unknown>
}

export interface TaskStatusEvent {
  type: 'task:status'
  timestamp: string
  run_id: string
  code?: string | null
  source_url: string
  status: DetailTaskStatus
  error?: string | null
}

export type CrawlerEvent = RunStatusEvent | RunProgressEvent | RunLogEvent | TaskStatusEvent

// ---- Connection status ----

export type SSEConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

// ---- SSE line parser ----

/**
 * Parse a single SSE ``data:`` line into a CrawlerEvent.
 * Returns ``null`` for non-data lines (comments, retry hints, heartbeats).
 */
export function parseSSELine(line: string): CrawlerEvent | null {
  // Skip empty lines, comments, and retry hints
  if (!line || line.startsWith(':') || line.startsWith('retry:')) {
    return null
  }

  // Extract data payload
  if (!line.startsWith('data: ')) {
    return null
  }

  const json = line.slice(6) // Remove 'data: ' prefix
  try {
    const parsed = JSON.parse(json) as CrawlerEvent
    if (parsed && typeof parsed === 'object' && 'type' in parsed) {
      return parsed
    }
  } catch {
    // Ignore malformed JSON
  }
  return null
}

/**
 * Parse a multi-line SSE message block into an array of CrawlerEvents.
 * SSE messages are separated by blank lines; each message may have
 * multiple ``data:`` lines that should be concatenated.
 */
export function parseSSEBlock(block: string): CrawlerEvent[] {
  const events: CrawlerEvent[] = []
  const lines = block.split('\n')
  let dataLines: string[] = []

  for (const line of lines) {
    if (line === '') {
      // End of message block — process accumulated data lines
      if (dataLines.length > 0) {
        const combined = dataLines.join('\n')
        const event = parseSSELine(`data: ${combined}`)
        if (event) events.push(event)
        dataLines = []
      }
    } else if (line.startsWith('data: ')) {
      dataLines.push(line.slice(6))
    }
    // Skip comments, retry, etc.
  }

  // Handle final block without trailing newline
  if (dataLines.length > 0) {
    const combined = dataLines.join('\n')
    const event = parseSSELine(`data: ${combined}`)
    if (event) events.push(event)
  }

  return events
}

// ---- Fetch-based EventSource ----

export interface CreateSSEConnectionOptions {
  /** JWT token for authentication */
  token: string
  /** Base URL origin (default: current origin) */
  origin?: string
  /** Callback for each parsed event */
  onEvent: (event: CrawlerEvent) => void
  /** Callback for connection status changes */
  onStatus?: (status: SSEConnectionStatus) => void
  /** Callback for errors */
  onError?: (error: Error) => void
  /** AbortSignal for external cancellation */
  signal?: AbortSignal
}

/**
 * Create an SSE connection using fetch() + ReadableStream.
 *
 * Returns an AbortController that can be used to close the connection.
 */
export function createSSEConnection(options: CreateSSEConnectionOptions): AbortController {
  const {
    token,
    origin = window.location.origin,
    onEvent,
    onStatus,
    onError,
    signal: externalSignal,
  } = options

  const controller = new AbortController()
  const url = `${origin}/api/crawler/stream?token=${encodeURIComponent(token)}`

  onStatus?.('connecting')

  void (async () => {
    try {
      const response = await fetch(url, {
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status} ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('SSE response body is null')
      }

      onStatus?.('connected')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!controller.signal.aborted) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process complete blocks (separated by double newlines)
        const blocks = buffer.split('\n\n')
        // Keep the last incomplete block in the buffer
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          if (block.trim()) {
            const events = parseSSEBlock(block)
            for (const event of events) {
              onEvent(event)
            }
          }
        }
      }

      onStatus?.('disconnected')
    } catch (err) {
      if (controller.signal.aborted) {
        onStatus?.('disconnected')
        return
      }

      const error = err instanceof Error ? err : new Error(String(err))
      onStatus?.('error')
      onError?.(error)
    }
  })()

  // Handle external abort signal
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort()
    } else {
      externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
    }
  }

  return controller
}
