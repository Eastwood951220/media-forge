/**
 * Tests for crawler SSE client utilities.
 */

import { describe, expect, it } from 'vitest'
import { parseSSEBlock, parseSSELine } from '../src/api/crawler/sse'
import type { CrawlerEvent } from '../src/api/crawler/sse'

describe('parseSSELine', () => {
  it('returns null for empty lines', () => {
    expect(parseSSELine('')).toBeNull()
  })

  it('returns null for comment lines', () => {
    expect(parseSSELine(': heartbeat')).toBeNull()
  })

  it('returns null for retry hints', () => {
    expect(parseSSELine('retry: 3000')).toBeNull()
  })

  it('returns null for lines without data prefix', () => {
    expect(parseSSELine('event: test')).toBeNull()
  })

  it('parses valid data line into CrawlerEvent', () => {
    const event = {
      type: 'run:status',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      status: 'running',
      task_name: 'Test Task',
    }

    const result = parseSSELine(`data: ${JSON.stringify(event)}`)

    expect(result).not.toBeNull()
    expect(result?.type).toBe('run:status')
    if (result?.type === 'run:status') {
      expect(result.run_id).toBe('run-1')
      expect(result.status).toBe('running')
    }
  })

  it('returns null for malformed JSON', () => {
    expect(parseSSELine('data: {invalid json}')).toBeNull()
  })

  it('returns null for JSON without type field', () => {
    expect(parseSSELine('data: {"foo": "bar"}')).toBeNull()
  })
})

describe('parseSSEBlock', () => {
  it('parses single event block', () => {
    const event = {
      type: 'run:progress',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      total: 10,
      saved: 5,
      failed: 0,
      skipped: 3,
      save_failed: 2,
    }

    const block = `data: ${JSON.stringify(event)}\n\n`
    const events = parseSSEBlock(block)

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('run:progress')
  })

  it('parses multiple events in one block', () => {
    const event1 = {
      type: 'run:status',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      status: 'running',
      task_name: 'Test',
    }

    const event2 = {
      type: 'run:progress',
      timestamp: '2026-07-03T00:01:00Z',
      run_id: 'run-1',
      total: 20,
      saved: 10,
      failed: 0,
      skipped: 5,
      save_failed: 5,
    }

    const block = `data: ${JSON.stringify(event1)}\n\ndata: ${JSON.stringify(event2)}\n\n`
    const events = parseSSEBlock(block)

    expect(events).toHaveLength(2)
    expect(events[0].type).toBe('run:status')
    expect(events[1].type).toBe('run:progress')
  })

  it('skips comment and retry lines', () => {
    const event = {
      type: 'run:log',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      level: 'INFO',
      message: 'Test log',
    }

    const block = `: heartbeat\nretry: 3000\ndata: ${JSON.stringify(event)}\n\n`
    const events = parseSSEBlock(block)

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('run:log')
  })

  it('handles block without trailing newline', () => {
    const event = {
      type: 'task:status',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      status: 'saved',
      source_url: 'https://example.test',
    }

    const block = `data: ${JSON.stringify(event)}`
    const events = parseSSEBlock(block)

    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('task:status')
  })

  it('returns empty array for blocks with only comments', () => {
    const block = ': heartbeat\n\n: keepalive\n\n'
    const events = parseSSEBlock(block)

    expect(events).toHaveLength(0)
  })
})

describe('CrawlerEvent types', () => {
  it('RunStatusEvent has correct shape', () => {
    const event: CrawlerEvent = {
      type: 'run:status',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      status: 'completed',
      task_name: 'Test Task',
      error: null,
    }

    expect(event.type).toBe('run:status')
    if (event.type === 'run:status') {
      expect(event.run_id).toBe('run-1')
      expect(event.status).toBe('completed')
    }
  })

  it('RunProgressEvent has correct shape', () => {
    const event: CrawlerEvent = {
      type: 'run:progress',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      total: 100,
      saved: 80,
      failed: 5,
      skipped: 10,
      save_failed: 5,
    }

    expect(event.type).toBe('run:progress')
    if (event.type === 'run:progress') {
      expect(event.total).toBe(100)
      expect(event.saved).toBe(80)
    }
  })

  it('RunLogEvent has correct shape', () => {
    const event: CrawlerEvent = {
      type: 'run:log',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      level: 'ERROR',
      message: 'Something failed',
      context: { code: 'AAA-001' },
    }

    expect(event.type).toBe('run:log')
    if (event.type === 'run:log') {
      expect(event.level).toBe('ERROR')
      expect(event.context?.code).toBe('AAA-001')
    }
  })

  it('TaskStatusEvent has correct shape', () => {
    const event: CrawlerEvent = {
      type: 'task:status',
      timestamp: '2026-07-03T00:00:00Z',
      run_id: 'run-1',
      code: 'AAA-001',
      source_url: 'https://example.test/aaa',
      status: 'saved',
      error: null,
    }

    expect(event.type).toBe('task:status')
    if (event.type === 'task:status') {
      expect(event.code).toBe('AAA-001')
      expect(event.status).toBe('saved')
    }
  })
})
