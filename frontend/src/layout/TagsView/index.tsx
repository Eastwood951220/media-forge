import { useCallback, useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { getFullPath, getRouteTagMeta, getRouteViewKey } from '@/routes/tags'
import type { RouteCacheControl } from '@/layout/routeCache'
import { useRouteCacheControl } from '@/layout/routeCache'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { TagView } from '@/stores/useTagsViewStore'
import { useTagsViewRegistration } from './hooks/useTagsViewRegistration'
import { useTagsContextMenu } from './hooks/useTagsContextMenu'
import { useTagsViewActions } from './hooks/useTagsViewActions'
import { TagsBar } from './components/TagsBar'
import { TagsContextMenu } from './components/TagsContextMenu'

type TagsViewProps = {
  darkMode?: boolean
  cacheControl?: RouteCacheControl
}

export function TagsView({ darkMode, cacheControl: cacheControlProp }: TagsViewProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const visitedViews = useTagsViewStore((state) => state.visitedViews)
  const routeCacheControl = useRouteCacheControl()
  const cacheControl = cacheControlProp ?? routeCacheControl

  const fullPath = getFullPath(pathname, searchStr)
  const cacheKey = getRouteViewKey(pathname, searchStr)
  const currentMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const isActive = useCallback((view: TagView) => view.cacheKey === cacheKey, [cacheKey])

  useTagsViewRegistration({
    cacheKey,
    currentMeta,
    fullPath,
    pathname,
    searchStr,
  })

  const context = useTagsContextMenu()
  const actions = useTagsViewActions({
    cacheControl,
    cacheKey,
    closeContextMenu: context.closeContextMenu,
    contextMenu: context.contextMenu,
    fullPath,
    navigate,
    visitedViews,
  })

  return (
    <>
      <TagsBar
        darkMode={darkMode}
        isActive={isActive}
        onClose={actions.handleClose}
        onContextMenu={context.handleContextMenu}
        onMouseDown={actions.handleMouseDown}
        onNavigate={(fullPath) => void navigate({ to: fullPath })}
        visitedViews={visitedViews}
      />
      <TagsContextMenu
        actions={actions}
        contextMenu={context.contextMenu}
        selectedTag={context.contextMenu.selectedTag}
        visitedViews={visitedViews}
      />
    </>
  )
}
