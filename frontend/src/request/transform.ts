import { message, Modal, notification } from 'antd'
import type { AxiosError, AxiosResponse } from 'axios'
import { HttpStatus } from '@/enums/RespEnum'
import { useAuthStore } from '@/store/useAuthStore'
import errorCode from '@/request/errorCode'
import { BusinessError } from './error'
import type { ApiResponse, RequestConfig } from './types'
import { isCancelledError } from './cancel'

/**
 * 是否已经展示重新登录弹窗。
 *
 * 使用对象而不是 boolean，保留外部可读写形态；
 * 多个接口同时返回 401 时，只允许第一个接口触发确认框。
 */
export const isRelogin = { show: false }

export function getBusinessMessage(data: ApiResponse): string {
  const code = data.code ?? HttpStatus.SUCCESS

  return errorCode[code as string | number] || data.msg || errorCode.default
}

function handleUnauthorized(msg: string): Promise<never> {
  if (!isRelogin.show) {
    isRelogin.show = true
    Modal.confirm({
      title: '系统提示',
      content: '登录状态已过期，您可以继续留在该页面，或者重新登录。',
      okText: '重新登录',
      cancelText: '取消',
      onOk: () => {
        isRelogin.show = false
        useAuthStore.getState().logout()
        window.location.href = '/login'
      },
      onCancel: () => {
        isRelogin.show = false
      },
    })
  }

  return Promise.reject(new Error(msg))
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

export const transformResponse = (response: AxiosResponse<ApiResponse>): unknown => {
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
    return response.data
  }

  if (code === HttpStatus.UNAUTHORIZED || code === String(HttpStatus.UNAUTHORIZED)) {
    return handleUnauthorized('无效的会话，或者会话已过期，请重新登录。')
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

  notification.error({ message: msg })
  return Promise.reject(new BusinessError(msg, code, response.data))
}

export function handleResponseError(error: AxiosError): Promise<never> {
  if (isCancelledError(error)) {
    return Promise.reject(error)
  }

  const requestConfig = error.config as RequestConfig | undefined
  const msg = normalizeNetworkError(error)

  if (requestConfig?.showError !== false) {
    void message.error(msg, 5)
  }

  return Promise.reject(error)
}
