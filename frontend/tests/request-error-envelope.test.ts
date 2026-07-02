import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosError } from 'axios'
import { message } from 'antd'
import { BusinessError } from '../src/request/error'
import { handleResponseError, isRelogin } from '../src/request/transform'

vi.mock('antd', () => ({
  message: { error: vi.fn(), warning: vi.fn() },
  notification: { error: vi.fn() },
  Modal: {
    confirm: vi.fn(),
  },
}))

function wrappedHttpError(status: number, data: unknown): AxiosError {
  return {
    name: 'AxiosError',
    message: `Request failed with status code ${status}`,
    isAxiosError: true,
    toJSON: () => ({}),
    config: {
      url: '/api/crawler/tasks',
      method: 'post',
      headers: {},
    },
    response: {
      status,
      statusText: 'Error',
      headers: {},
      config: {
        url: '/api/crawler/tasks',
        method: 'post',
        headers: {},
      },
      data,
    },
  } as AxiosError
}

describe('request error envelope handling', () => {
  beforeEach(() => {
    isRelogin.show = false
    vi.clearAllMocks()
  })

  it('uses backend msg from non-2xx wrapped response', async () => {
    const error = wrappedHttpError(409, {
      code: 409,
      msg: "任务名称 '巨乳' 已存在",
      data: null,
    })

    await expect(handleResponseError(error)).rejects.toMatchObject({
      name: 'BusinessError',
      message: "任务名称 '巨乳' 已存在",
      code: 409,
    } satisfies Partial<BusinessError>)

    expect(message.error).toHaveBeenCalledWith("任务名称 '巨乳' 已存在", 5)
  })

  it('falls back to legacy detail when response is not wrapped', async () => {
    const error = wrappedHttpError(400, {
      detail: 'URL 重复: https://javdb.com/actors/QV49G',
    })

    await expect(handleResponseError(error)).rejects.toThrow('URL 重复: https://javdb.com/actors/QV49G')
  })
})
