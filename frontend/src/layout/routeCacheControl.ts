import { createContext, useContext } from 'react'
import type { useKeepAliveRef } from 'keepalive-for-react'

export const ROUTE_CACHE_EXCLUDE_PATHS = ['/login', '/init']

export type RouteCacheControl = {
  destroy: (cacheKey: string) => Promise<void>
  destroyMany: (cacheKeys: string[]) => Promise<void>
  destroyOther: (cacheKey: string) => Promise<void>
  destroyAll: () => Promise<void>
  refresh: (cacheKey?: string) => void
}

const noopRouteCacheControl: RouteCacheControl = {
  destroy: async () => undefined,
  destroyMany: async () => undefined,
  destroyOther: async () => undefined,
  destroyAll: async () => undefined,
  refresh: () => undefined,
}

export const RouteCacheControlContext = createContext<RouteCacheControl>(noopRouteCacheControl)

export const RouteCacheRefContext = createContext<ReturnType<typeof useKeepAliveRef> | null>(null)

export function isRouteCacheExcluded(pathname: string) {
  return ROUTE_CACHE_EXCLUDE_PATHS.includes(pathname)
}

export function useRouteCacheControl() {
  return useContext(RouteCacheControlContext)
}
