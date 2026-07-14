import {cancelRequest, removeRequestController} from './cancel'
import {getRequestCache} from './cache'
import {service} from './instance'
import type {RepeatStrategy, RequestConfig, RequestPendingRecord} from './types'
import {getRequestKey, getRequestMethod} from './utils'

const pendingRequests = new Map<string, RequestPendingRecord>()

export function getRepeatStrategy(config: RequestConfig): RepeatStrategy {
    if (config.repeatStrategy) {
        return config.repeatStrategy
    }

    if (config.isDedupe === false) {
        return 'none'
    }

    return getRequestMethod(config) === 'get' ? 'reuse' : 'none'
}

export function requestWithStrategy<T = unknown>(config: RequestConfig): Promise<T> {
    const strategy = getRepeatStrategy(config)
    const key = getRequestKey(config)

    if (getRequestMethod(config) === 'get' && config.cache) {
        const cached = getRequestCache<T>(config.cacheKey || key)
        if (cached !== undefined) {
            return Promise.resolve(cached)
        }
    }

    if (strategy === 'none') {
        return service.request<T, T>(config)
    }

    const pending = pendingRequests.get(key)

    if (strategy === 'reuse' || strategy === 'ignore-new') {
        if (pending) {
            return pending.promise as Promise<T>
        }
    }

    if (strategy === 'cancel-prev' && pending) {
        cancelRequest(key, '取消上一次相同请求')
    }

    const promise = service.request<T, T>(config).finally(() => {
        pendingRequests.delete(key)
        removeRequestController(key)
    })

    pendingRequests.set(key, {promise})
    return promise
}
