import {getToken} from '@/utils/auth'
import {cancelAllRequests, cancelRequest, cancelRequestGroup, removeRequestController} from './cancel'
import {getRequestCache} from './cache'
import {download} from './download'
import {service} from './instance'
import {setupInterceptors} from './interceptors'
import type {ApiResponse, RepeatStrategy, RequestConfig, RequestPendingRecord} from './types'
import {getRequestKey, getRequestMethod} from './utils'

const AUTHORIZATION_HEADER = 'Authorization'

// 注册拦截器（模块加载时执行一次）
setupInterceptors(service)

/** 外部特殊场景可复用的全局请求头。 */
export function globalHeaders(): Record<string, string> {
	const token = getToken()
	
	return {
		...(token ? {[AUTHORIZATION_HEADER]: `Bearer ${token}`} : {}),
	}
}

// ---- 重复请求策略 ----

const pendingRequests = new Map<string, RequestPendingRecord>()

function getRepeatStrategy(config: RequestConfig): RepeatStrategy {
	if (config.repeatStrategy) {
		return config.repeatStrategy
	}
	
	if (config.isDedupe === false) {
		return 'none'
	}
	
	return getRequestMethod(config) === 'get' ? 'reuse' : 'none'
}

function requestWithStrategy<T = unknown>(config: RequestConfig): Promise<T> {
	const strategy = getRepeatStrategy(config)
	const key = getRequestKey(config)
	
	// 缓存命中（GET + cache 启用时已在拦截器处理，这里做二次保险）
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

// ---- request 主函数 ----

export const request = Object.assign(
	<T = unknown>(config: RequestConfig): Promise<T> => requestWithStrategy<T>(config),
	{
		get<T = unknown>(
			url: string,
			params?: unknown,
			config?: RequestConfig,
		): Promise<T> {
			return requestWithStrategy<T>({
				...config,
				url,
				method: 'get',
				params,
			})
		},
		
		post<T = unknown>(
			url: string,
			data?: unknown,
			config?: RequestConfig,
		): Promise<T> {
			return requestWithStrategy<T>({
				...config,
				url,
				method: 'post',
				data,
			})
		},
		
		put<T = unknown>(
			url: string,
			data?: unknown,
			config?: RequestConfig,
		): Promise<T> {
			return requestWithStrategy<T>({
				...config,
				url,
				method: 'put',
				data,
			})
		},
		
		delete<T = unknown>(
			url: string,
			params?: unknown,
			config?: RequestConfig,
		): Promise<T> {
			return requestWithStrategy<T>({
				...config,
				url,
				method: 'delete',
				params,
			})
		},
	},
)

export {download}

export {cancelRequest, cancelRequestGroup, cancelAllRequests}

export {removeRequestCache, clearRequestCache} from './cache'

export {BusinessError} from './error'

export {isRelogin} from './transform'

export type {ApiResponse, RequestConfig, RepeatStrategy}

export default request
