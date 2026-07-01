import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { getToken } from '@/utils/auth'
import type { PlusInternalRequestConfig, RequestConfig } from './types'
import { createRequestSignal, removeRequestController } from './cancel'
import { getRequestCache, setRequestCache } from './cache'
import { decryptResponseData, encryptRequestData } from './crypto'
import { checkRepeatSubmit } from './repeatSubmit'
import { handleResponseError, transformResponse } from './transform'
import {
  clearInternalHeaders,
  getRequestMethod,
  getRequestKey,
  getHeaderValue,
  isFalseLike,
  normalizeFormDataHeaders,
  normalizeGetParams,
} from './utils'

const AUTHORIZATION_HEADER = 'Authorization'
const CLIENT_ID_HEADER = 'clientid'
const clientId = import.meta.env.VITE_APP_CLIENT_ID || ''

export function setupInterceptors(service: AxiosInstance): void {
  service.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const requestConfig = config as PlusInternalRequestConfig

      // Token 注入
      const token = getToken()
      const isTokenFalse = isFalseLike(getHeaderValue(requestConfig, 'isToken'))

      if (token && !isTokenFalse && requestConfig.isToken !== false) {
        requestConfig.headers.set(AUTHORIZATION_HEADER, `Bearer ${token}`)
      }

      // clientid 注入
      if (clientId) {
        requestConfig.headers.set(CLIENT_ID_HEADER, clientId)
      }

      // GET 参数拼接到 URL
      normalizeGetParams(requestConfig)

      // 重复提交检查
      if (checkRepeatSubmit(requestConfig)) {
        return Promise.reject(new Error('数据正在处理，请勿重复提交'))
      }

      // 请求加密
      encryptRequestData(requestConfig)

      // FormData 删除 Content-Type
      normalizeFormDataHeaders(requestConfig)

      // 创建取消信号
      const signal = createRequestSignal(requestConfig as RequestConfig)
      if (signal) {
        requestConfig.signal = signal
      }

      // GET 缓存检查
      const method = getRequestMethod(requestConfig)
      if (method === 'get' && requestConfig.cache) {
        const cacheKey = requestConfig.cacheKey || getRequestKey(requestConfig as RequestConfig)
        const cached = getRequestCache(cacheKey)
        if (cached !== undefined) {
          // 通过 adapter 返回缓存数据，跳过实际请求
          requestConfig.adapter = () => {
            return Promise.resolve({
              data: cached,
              status: 200,
              statusText: 'OK',
              headers: {},
              config: requestConfig,
            })
          }
        }
      }

      // 清理内部控制头
      clearInternalHeaders(requestConfig)

      return requestConfig
    },
    (error) => Promise.reject(error),
  )

  service.interceptors.response.use(
    (response) => {
      const config = response.config as RequestConfig

      // 响应解密
      decryptResponseData(response)

      // GET 缓存写入
      if (
        getRequestMethod(config) === 'get' &&
        config.cache &&
        response.status === 200
      ) {
        const cacheKey = config.cacheKey || getRequestKey(config)
        setRequestCache(cacheKey, response.data, config.cacheTime)
      }

      // 清理 cancel controller
      const key = getRequestKey(config)
      removeRequestController(key)

      return transformResponse(response) as typeof response
    },
    (error) => {
      // 清理 cancel controller
      if (error.config) {
        const key = getRequestKey(error.config as RequestConfig)
        removeRequestController(key)
      }

      return handleResponseError(error)
    },
  )
}
