import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatDateTime } from './dateTime'

afterEach(() => vi.unstubAllEnvs())

describe('formatDateTime', () => {
  it('converts UTC timestamps to local time in 24-hour format', () => {
    vi.stubEnv('TZ', 'Asia/Shanghai')
    expect(formatDateTime('2026-11-05T08:35:03.079Z')).toBe('2026-11-05 16:35:03')
    expect(formatDateTime('2026-11-05T16:00:00Z')).toBe('2026-11-06 00:00:00')
  })

  it('uses the device timezone rather than a fixed offset', () => {
    vi.stubEnv('TZ', 'UTC')
    expect(formatDateTime('2026-11-05T08:35:03Z')).toBe('2026-11-05 08:35:03')
  })

  it('shows a placeholder for missing or invalid timestamps', () => {
    for (const value of [undefined, null, '', 'invalid date']) {
      expect(formatDateTime(value)).toBe('-')
    }
  })
})
