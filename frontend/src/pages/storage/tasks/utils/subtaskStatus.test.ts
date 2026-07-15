import { describe, expect, it } from 'vitest'
import { formatTime } from './subtaskStatus'

describe('storage subtask log formatTime', () => {
  it('formats legacy timezone-less storage log timestamps as Beijing time', () => {
    expect(formatTime('2026-07-04T03:41:43.132033')).toBe('11:41:43')
  })

  it('formats UTC timestamps with explicit Z suffix as Beijing time', () => {
    expect(formatTime('2026-07-04T03:41:43.132Z')).toBe('11:41:43')
  })

  it('formats timestamps with explicit offsets as Beijing time', () => {
    expect(formatTime('2026-07-04T10:41:43.132+07:00')).toBe('11:41:43')
  })

  it('returns invalid timestamp values unchanged', () => {
    expect(formatTime('not-a-date')).toBe('not-a-date')
  })
})
