import { message, notification } from 'antd'
import type { AxiosError, AxiosResponse } from 'axios'
import { HttpStatus } from '@/enums/RespEnum'
import { BusinessError } from './error'
import type { ApiResponse, PaginatedApiResponse, RequestConfig } from './types'
import { isCancelledError } from './cancel'
import { expireSession } from './session'
import { getBusinessMessage } from './businessError'
import { getResponseErrorPayload } from './networkError'

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
