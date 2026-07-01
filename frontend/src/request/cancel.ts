import type { RequestConfig } from './types'
import { getRequestKey } from './utils'

type CancelRecord = {
  controller: AbortController
  key: string
  group?: string
}

const cancelMap = new Map<string, CancelRecord>()
const groupMap = new Map<string, Set<string>>()

/**
 * 为请求创建 AbortSignal。
 *
 * - config.isCancelable === false 时不创建 AbortController
 * - 外部已传入 config.signal 时，尊重外部 signal
 * - 如果配置了 cancelGroup，加入 groupMap
 */
export function createRequestSignal(
  config: RequestConfig,
): AbortSignal | undefined {
  if (config.isCancelable === false) {
    return config.signal as AbortSignal | undefined
  }

  const key = getRequestKey(config)
  const controller = new AbortController()

  cancelMap.set(key, { controller, key, group: config.cancelGroup })

  if (config.cancelGroup) {
    let group = groupMap.get(config.cancelGroup)
    if (!group) {
      group = new Set()
      groupMap.set(config.cancelGroup, group)
    }
    group.add(key)
  }

  if (config.signal) {
    const externalSignal = config.signal as AbortSignal
    externalSignal.addEventListener('abort', () => {
      controller.abort(externalSignal.reason)
    })
  }

  return controller.signal
}

export function cancelRequest(key: string, reason = '请求已取消'): void {
  const record = cancelMap.get(key)

  if (record) {
    record.controller.abort(reason)
    cancelMap.delete(key)

    if (record.group) {
      const group = groupMap.get(record.group)
      if (group) {
        group.delete(key)
        if (group.size === 0) {
          groupMap.delete(record.group)
        }
      }
    }
  }
}

export function cancelRequestGroup(group: string, reason = '请求组已取消'): void {
  const keys = groupMap.get(group)

  if (keys) {
    for (const key of keys) {
      const record = cancelMap.get(key)
      if (record) {
        record.controller.abort(reason)
        cancelMap.delete(key)
      }
    }
    groupMap.delete(group)
  }
}

export function cancelAllRequests(reason = '全部请求已取消'): void {
  for (const [, record] of cancelMap) {
    record.controller.abort(reason)
  }
  cancelMap.clear()
  groupMap.clear()
}

/** 请求完成后清理 controller。 */
export function removeRequestController(key: string): void {
  const record = cancelMap.get(key)

  if (record) {
    cancelMap.delete(key)

    if (record.group) {
      const group = groupMap.get(record.group)
      if (group) {
        group.delete(key)
        if (group.size === 0) {
          groupMap.delete(record.group)
        }
      }
    }
  }
}

export function isCancelledError(error: unknown): boolean {
  if (error instanceof Error) {
    return error.name === 'CanceledError' || error.name === 'AbortError'
  }
  if (typeof error === 'object' && error !== null) {
    const axiosError = error as { code?: string; message?: string }
    return axiosError.code === 'ERR_CANCELED'
  }
  return false
}
