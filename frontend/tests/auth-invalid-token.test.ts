import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AxiosError } from 'axios'
import { handleResponseError, isRelogin } from '../src/request/transform'
import { useAuthStore } from '../src/stores/useAuthStore'
import { getToken, setToken } from '../src/utils/auth'

vi.mock('antd', () => ({
  message: { error: vi.fn() },
  notification: { error: vi.fn() },
  Modal: {
    confirm: vi.fn(),
  },
}))

function http401Error(): AxiosError {
  return {
    name: 'AxiosError',
    message: 'Request failed with status code 401',
    isAxiosError: true,
    toJSON: () => ({}),
    config: {
      url: '/api/crawler/tasks',
      method: 'get',
      headers: {},
    },
    response: {
      status: 401,
      statusText: 'Unauthorized',
      headers: {},
      config: {
        url: '/api/crawler/tasks',
        method: 'get',
        headers: {},
      },
      data: { detail: 'Invalid or expired token' },
    },
  } as AxiosError
}

describe('HTTP 401 invalid token handling', () => {
  beforeEach(() => {
    isRelogin.show = false
    setToken('expired-token')
    useAuthStore.setState({
      token: 'expired-token',
      isAuthenticated: true,
      userInfo: null,
    })
  })

  it('clears stale auth state when FastAPI returns bare HTTP 401', async () => {
    await expect(handleResponseError(http401Error())).rejects.toThrow('Invalid or expired token')

    expect(getToken()).toBeNull()
    expect(useAuthStore.getState().token).toBe('')
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
})
