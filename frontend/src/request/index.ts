import {cancelAllRequests, cancelRequest, cancelRequestGroup} from './cancel'
import {download} from './download'
import {setupInterceptors} from './interceptors'
import {globalHeaders} from './headers'
import {requestWithStrategy} from './repeatStrategy'
import {service} from './instance'
import type {ApiResponse, PaginatedApiResponse, RepeatStrategy, RequestConfig} from './types'

// 注册拦截器（模块加载时执行一次）
setupInterceptors(service)

export {globalHeaders}

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

export type {ApiResponse, PaginatedApiResponse, RequestConfig, RepeatStrategy}

export default request
