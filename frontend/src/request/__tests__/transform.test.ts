import { describe, expect, it } from 'vitest'
import type { AxiosError, AxiosResponse } from 'axios'
import { normalizeNetworkError, transformResponse } from '../transform'

function response(data: unknown, config: Record<string, unknown> = {}): AxiosResponse {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: { headers: {}, ...config },
    request: { responseType: 'json' },
  } as unknown as AxiosResponse
}

describe('request transform', () => {
  it('unwraps successful object responses', () => {
    expect(transformResponse(response({ code: 200, msg: 'ok', data: { id: 1 } }))).toEqual({ id: 1 })
  })

  it('keeps paginated responses intact', () => {
    expect(transformResponse(response({ code: 200, msg: 'ok', rows: [{ id: 1 }], total: 1 }))).toEqual({
      code: 200,
      msg: 'ok',
      rows: [{ id: 1 }],
      total: 1,
    })
  })

  it('normalizes network errors', () => {
    expect(normalizeNetworkError({ message: 'Network Error' } as AxiosError)).toBe('后端接口连接异常')
  })
})
