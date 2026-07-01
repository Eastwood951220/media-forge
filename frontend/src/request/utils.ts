import { isEmpty, isNil, isPlainObject, isUndefined, toString } from 'lodash'
import type { PlusInternalRequestConfig, RequestConfig } from './types'

/**
 * 将普通对象序列化成 RuoYi 后端常用的查询字符串格式。
 *
 * - null、undefined、空字符串不参与提交；
 * - 普通对象会展开为 a[b]=1；
 * - 数组按重复 key 提交。
 */
export function tansParams(params: Record<string, unknown>): string {
  const result = new URLSearchParams()

  Object.entries(params).forEach(([propName, value]) => {
    if (isNil(value) || value === '') {
      return
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (!isNil(item) && item !== '') {
          result.append(propName, toString(item))
        }
      })
      return
    }

    if (isPlainObject(value)) {
      Object.entries(value as Record<string, unknown>).forEach(
        ([key, childValue]) => {
          if (!isNil(childValue) && childValue !== '') {
            result.append(`${propName}[${key}]`, toString(childValue))
          }
        },
      )
      return
    }

    result.append(propName, toString(value))
  })

  return result.toString()
}

/** 确定性 JSON 序列化，用于生成稳定的缓存/去重 key。 */
export function stableStringify(value: unknown): string {
  if (isNil(value)) {
    return ''
  }

  if (value instanceof FormData) {
    return '[FormData]'
  }

  if (value instanceof URLSearchParams) {
    return value.toString()
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`
  }

  if (isPlainObject(value)) {
    return JSON.stringify(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((result, key) => {
          const childValue = (value as Record<string, unknown>)[key]

          result[key] = isPlainObject(childValue) || Array.isArray(childValue)
            ? stableStringify(childValue)
            : childValue
          return result
        }, {}),
    )
  }

  return toString(value)
}

/** 统一获取请求 method（小写）。 */
export function getRequestMethod(config: RequestConfig): string {
  return (config.method || 'get').toLowerCase()
}

/** 生成请求唯一标识 key。 */
export function getRequestKey(config: RequestConfig): string {
  const method = getRequestMethod(config)
  const url = config.url || ''
  const params = stableStringify(config.params)
  const data = stableStringify(config.data)
  const baseURL = config.baseURL || ''

  return [method, baseURL, url, params, data].join('&')
}

/**
 * Axios v1 的 headers 可能是 AxiosHeaders，也可能被外部传入普通对象。
 * 统一读取，避免在拦截器中到处做类型分支。
 */
export function getHeaderValue(config: PlusInternalRequestConfig, key: string): unknown {
  const getter = (config.headers as { get?: (name: string) => unknown }).get
  const value = getter?.call(config.headers, key)

  if (!isUndefined(value)) {
    return value
  }

  return (config.headers as unknown as Record<string, unknown>)[key]
}

/** 内部控制头只用于前端拦截器，不应该透传给后端。 */
export function deleteHeader(config: PlusInternalRequestConfig, key: string): void {
  const deleter = (config.headers as { delete?: (name: string) => void }).delete

  if (deleter) {
    deleter.call(config.headers, key)
    return
  }

  delete (config.headers as unknown as Record<string, unknown>)[key]
}

export function isFalseLike(value: unknown): boolean {
  return value === false || value === 'false'
}

export function isTrueLike(value: unknown): boolean {
  return value === true || value === 'true'
}

/**
 * GET 请求参数统一拼接到 URL。
 * 与 RuoYi 后端保持一致：后端接收的是 query string。
 */
export function normalizeGetParams(config: PlusInternalRequestConfig): void {
  const method = getRequestMethod(config)

  if (
    method !== 'get' ||
    !isPlainObject(config.params) ||
    isEmpty(config.params)
  ) {
    return
  }

  const queryString = tansParams(config.params as Record<string, unknown>)

  if (queryString) {
    config.url = `${config.url}${
      config.url?.includes('?') ? '&' : '?'
    }${queryString}`
    config.params = {}
  }
}

/**
 * FormData 必须让浏览器自行设置 multipart boundary。
 * 如果保留 application/json，后端会无法正确解析文件流。
 */
export function normalizeFormDataHeaders(config: PlusInternalRequestConfig): void {
  if (config.data instanceof FormData) {
    deleteHeader(config, 'Content-Type')
  }
}

/** 清理只给前端拦截器消费的控制头。 */
export function clearInternalHeaders(config: PlusInternalRequestConfig): void {
  ;['isToken', 'repeatSubmit', 'interval'].forEach((key) => {
    deleteHeader(config, key)
  })
}
