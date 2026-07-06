import { useCallback } from 'react'
import type { TagView } from '@/stores/useTagsViewStore'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { RouteCacheControl } from '@/layout/routeCache'
import type { ContextMenuState } from './useTagsContextMenu'
import { getRemovedCacheKeys } from '../tagsViewUtils'

export function useTagsViewActions({
  cacheControl,
  cacheKey,
  closeContextMenu,
  contextMenu,
  fullPath,
  navigate,
  visitedViews,
}: {
  cacheControl: RouteCacheControl
  cacheKey: string
  closeContextMenu: () => void
  contextMenu: ContextMenuState
  fullPath: string
  navigate: (opts: { to: string; replace?: boolean }) => Promise<void> | void
  visitedViews: TagView[]
}) {
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const removeOtherViews = useTagsViewStore((state) => state.removeOtherViews)
  const removeLeftViews = useTagsViewStore((state) => state.removeLeftViews)
  const removeRightViews = useTagsViewStore((state) => state.removeRightViews)
  const removeAllViews = useTagsViewStore((state) => state.removeAllViews)

  const navigateAfterClose = useCallback(
    (views: TagView[]) => {
      if (views.some((view) => view.cacheKey === cacheKey)) return
      const last = views.at(-1)
      void navigate({ to: last?.fullPath ?? '/' })
    },
    [cacheKey, navigate],
  )

  const destroyRemovedCaches = useCallback(
    (beforeViews: TagView[], nextViews: TagView[]) => {
      const removedCacheKeys = getRemovedCacheKeys(beforeViews, nextViews)
      void cacheControl.destroyMany(removedCacheKeys)
    },
    [cacheControl],
  )

  const handleClose = useCallback(
    (tag: TagView, event?: React.MouseEvent) => {
      event?.stopPropagation()
      if (tag.closable === false) return
      const nextViews = removeSelectedView(tag)
      void cacheControl.destroy(tag.cacheKey)
      navigateAfterClose(nextViews)
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleMouseDown = useCallback(
    (tag: TagView, event: React.MouseEvent) => {
      if (event.button === 1 && tag.closable !== false) {
        event.preventDefault()
        const nextViews = removeSelectedView(tag)
        void cacheControl.destroy(tag.cacheKey)
        navigateAfterClose(nextViews)
      }
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleRefresh = useCallback(() => {
    closeContextMenu()
    cacheControl.refresh(contextMenu.selectedTag?.cacheKey ?? cacheKey)
    void navigate({ to: fullPath, replace: true })
  }, [cacheControl, cacheKey, closeContextMenu, contextMenu.selectedTag, fullPath, navigate])

  const handleCloseCurrent = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag || tag.closable === false) return
    const nextViews = removeSelectedView(tag)
    void cacheControl.destroy(tag.cacheKey)
    navigateAfterClose(nextViews)
  }, [
    cacheControl,
    closeContextMenu,
    contextMenu.selectedTag,
    navigateAfterClose,
    removeSelectedView,
  ])

  const handleCloseOthers = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeOtherViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeOtherViews,
    visitedViews,
  ])

  const handleCloseLeft = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeLeftViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeLeftViews,
    visitedViews,
  ])

  const handleCloseRight = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag) return
    const beforeViews = visitedViews
    const nextViews = removeRightViews(tag)
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    contextMenu.selectedTag,
    destroyRemovedCaches,
    navigateAfterClose,
    removeRightViews,
    visitedViews,
  ])

  const handleCloseAll = useCallback(() => {
    closeContextMenu()
    const beforeViews = visitedViews
    const nextViews = removeAllViews()
    destroyRemovedCaches(beforeViews, nextViews)
    navigateAfterClose(nextViews)
  }, [
    closeContextMenu,
    destroyRemovedCaches,
    navigateAfterClose,
    removeAllViews,
    visitedViews,
  ])

  return {
    handleClose,
    handleMouseDown,
    handleRefresh,
    handleCloseCurrent,
    handleCloseOthers,
    handleCloseLeft,
    handleCloseRight,
    handleCloseAll,
  }
}
