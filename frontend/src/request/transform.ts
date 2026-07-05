import { message, Modal, notification } from 'antd'
import type { AxiosError, AxiosResponse } from 'axios'
import { HttpStatus } from '@/enums/RespEnum'
import { useAuthStore } from '@/stores/useAuthStore.ts'
import errorCode from '@/request/errorCode'
import { BusinessError } from './error'
import type { ApiResponse, PaginatedApiResponse, RequestConfig } from './types'
import { isCancelledError } from './cancel'

/**
 * 是否已经展示重新登录弹窗。
 *
 * 使用对象而不是 boolean，保留外部可读写形态；
 * 多个接口同时返回 401 时，只允许第一个接口触发确认框。
 */
export const isRelogin = { show: false }

export function getBusinessMessage(data: ApiResponse | PaginatedApiResponse): string {
  const code = data.code ?? HttpStatus.SUCCESS
  return errorCode[code as string | number] || data.msg || errorCode.default
}

function loginRedirectUrl(): string {
  const current = `${window.location.pathname}${window.location.search}`
  const params = new URLSearchParams()
  if (current && current !== '/login') {
    params.set('redirect', current)
  }
  const query = params.toString()
  return query ? `/login?${query}` : '/login'
}

function expireSession(msg: string): Promise<never> {
  useAuthStore.getState().logout()

  if (!isRelogin.show) {
    isRelogin.show = true
    Modal.confirm({
      title: '系统提示',
      content: '登录状态已过期，请重新登录。',
      okText: '重新登录',
      cancelText: '取消',
      onOk: () => {
        isRelogin.show = false
        window.location.href = loginRedirectUrl()
      },
      onCancel: () => {
        isRelogin.show = false
      },
    })
  }

  return Promise.reject(new Error(msg))
}


function getResponseErrorPayload(error: AxiosError): {
  msg: string
  code?: string | number
  data?: unknown
} {
  const data = error.response?.data

  if (data && typeof data === 'object') {
    if ('msg' in data) {
      const wrapped = data as Partial<ApiResponse>
      const code = wrapped.code ?? error.response?.status
      const msg = wrapped.msg || errorCode[code as string | number] || errorCode.default
      return { msg, code, data }
    }

    if ('detail' in data) {
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') {
        return { msg: detail, code: error.response?.status, data }
      }
    }
  }

  return {
    msg: normalizeNetworkError(error),
    code: error.response?.status,
    data,
  }
}

export function normalizeNetworkError(error: AxiosError): string {
  const msg = error.message

  if (msg === 'Network Error') {
    return '后端接口连接异常'
  }

  if (msg.includes('timeout')) {
    return '系统接口请求超时'
  }

  if (msg.includes('Request failed with status code')) {
    return `系统接口${msg.substring(msg.length - 3)}异常`
  }

  if (error.response?.status) {
    return `系统接口${error.response.status}异常`
  }

  return msg || errorCode.default
}

export const transformResponse = (response: AxiosResponse<ApiResponse | PaginatedApiResponse>): unknown => {
  const config = response.config as RequestConfig

  if (config.isReturnNativeResponse === true) {
    return response
  }

  // decryptResponseData 已在 interceptors.ts 中调用

  if (
    response.request.responseType === 'blob' ||
    response.request.responseType === 'arraybuffer'
  ) {
    return response.data
  }

  if (config.isTransformResponse === true) {
    return response.data
  }

  const code = response.data.code ?? HttpStatus.SUCCESS
  const msg = getBusinessMessage(response.data)

  if (code === HttpStatus.SUCCESS || code === String(HttpStatus.SUCCESS)) {
    // 判断是分页响应还是普通响应
    const data = response.data as PaginatedApiResponse
    if ('rows' in data && 'total' in data) {
      // 分页响应：返回 {rows, total, code, msg}
      return data
    }
    // 普通响应：返回 data 字段
    return (response.data as ApiResponse).data
  }

  if (code === HttpStatus.UNAUTHORIZED || code === String(HttpStatus.UNAUTHORIZED)) {
    return expireSession('无效的会话，或者会话已过期，请重新登录。')
  }

  if (config.showError === false) {
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  if (code === HttpStatus.SERVER_ERROR || code === String(HttpStatus.SERVER_ERROR)) {
    void message.error(msg)
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  if (code === HttpStatus.WARN || code === String(HttpStatus.WARN)) {
    void message.warning(msg)
    return Promise.reject(new BusinessError(msg, code, response.data))
  }

  notification.error({ description: msg })
  return Promise.reject(new BusinessError(msg, code, response.data))
}

export function handleResponseError(error: AxiosError): Promise<never> {
  if (isCancelledError(error)) {
    return Promise.reject(error)
  }

  const requestConfig = error.config as RequestConfig | undefined
  const payload = getResponseErrorPayload(error)

  if (error.response?.status === HttpStatus.UNAUTHORIZED) {
    return expireSession(payload.msg)
  }

  if (requestConfig?.showError !== false) {
    void message.error(payload.msg, 5)
  }

  return Promise.reject(new BusinessError(payload.msg, payload.code, payload.data))
}
