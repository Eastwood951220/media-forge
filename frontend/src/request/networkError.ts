import type { AxiosError } from 'axios'
import errorCode from '@/request/errorCode'
import type { ApiResponse } from './types'

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

export function getResponseErrorPayload(error: AxiosError): {
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
