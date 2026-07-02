import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'

export interface ApiResponse<T = unknown> {
  code: number
  msg: string
  data?: T
}

export interface PaginatedApiResponse<T = unknown> {
  code: number
  msg: string
  rows: T[]
  total: number
}

export type RepeatStrategy = 'reuse' | 'cancel-prev' | 'ignore-new' | 'none'

export interface RequestConfig extends AxiosRequestConfig {
  /** false 时不注入 Authorization。兼容 headers.isToken = false。 */
  isToken?: boolean

  /** true 时启用重复提交拦截。兼容 headers.repeatSubmit = false 关闭拦截。 */
  isRepeatSubmit?: boolean

  /** 单接口自定义重复提交间隔。 */
  repeatSubmitInterval?: number

  /** true 时直接返回 AxiosResponse。 */
  isReturnNativeResponse?: boolean

  /** true 时直接返回 response.data，不做业务 code 判断。 */
  isTransformResponse?: boolean

  /** false 时关闭进行中相同请求去重。 */
  isDedupe?: boolean

  /** 是否允许请求取消。默认 true。 */
  isCancelable?: boolean

  /** 请求取消分组。常用于页面级取消。 */
  cancelGroup?: string

  /**
   * 重复请求处理策略。
   *
   * - reuse: 复用进行中的相同请求 Promise
   * - cancel-prev: 取消上一次相同请求，然后发起新请求
   * - ignore-new: 忽略新请求，直接返回旧请求 Promise
   * - none: 不处理重复请求
   *
   * 默认：GET 使用 reuse；其他方法使用 none。
   */
  repeatStrategy?: RepeatStrategy

  /** 是否展示全局错误提示。默认 true。 */
  showError?: boolean

  /** 是否启用 GET 结果缓存。默认 false。 */
  cache?: boolean

  /** 缓存时间，单位 ms。 */
  cacheTime?: number

  /** 自定义缓存 key。 */
  cacheKey?: string
}

export type PlusInternalRequestConfig = InternalAxiosRequestConfig & RequestConfig

export type RepeatSubmitRecord = {
  url?: string
  data?: string
  time: number
}

export type RequestPendingRecord = {
  promise: Promise<unknown>
}
