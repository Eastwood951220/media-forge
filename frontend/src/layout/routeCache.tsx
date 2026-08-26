import { useContext, useMemo, type PropsWithChildren } from 'react'
import { Outlet, useRouterState } from '@tanstack/react-router'
import { KeepAlive, useKeepAliveRef } from 'keepalive-for-react'
import { getRouteViewKey } from '@/routes/tags'
import {
  ROUTE_CACHE_EXCLUDE_PATHS,
  RouteCacheControlContext,
  RouteCacheRefContext,
  isRouteCacheExcluded,
  type RouteCacheControl,
} from './routeCacheControl'

export function RouteKeepAliveProvider({ children }: PropsWithChildren) {
  const aliveRef = useKeepAliveRef()

  const cacheControl = useMemo<RouteCacheControl>(
    () => ({
      destroy: async (cacheKey) => {
        await aliveRef.current?.destroy(cacheKey)
      },
      destroyMany: async (cacheKeys) => {
        if (cacheKeys.length > 0) {
          await aliveRef.current?.destroy(cacheKeys)
        }
      },
      destroyOther: async (cacheKey) => {
        await aliveRef.current?.destroyOther(cacheKey)
      },
      destroyAll: async () => {
        await aliveRef.current?.destroyAll()
      },
      refresh: (cacheKey) => {
        aliveRef.current?.refresh(cacheKey)
      },
    }),
    [aliveRef],
  )

  return (
    <RouteCacheRefContext.Provider value={aliveRef}>
      <RouteCacheControlContext.Provider value={cacheControl}>
        {children}
      </RouteCacheControlContext.Provider>
    </RouteCacheRefContext.Provider>
  )
}

export function RouteKeepAliveOutlet() {
  const aliveRef = useContext(RouteCacheRefContext)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const activeCacheKey = getRouteViewKey(pathname, searchStr)

  if (isRouteCacheExcluded(pathname) || !aliveRef) {
    return <Outlet />
  }

  return (
    <KeepAlive
      activeCacheKey={activeCacheKey}
      aliveRef={aliveRef}
      exclude={ROUTE_CACHE_EXCLUDE_PATHS}
      max={18}
    >
      <Outlet key={activeCacheKey} />
    </KeepAlive>
  )
}
