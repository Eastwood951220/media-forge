import type { TagView } from '@/stores/useTagsViewStore'

/** TagsView whitelist - these paths are not shown as tags */
export const TAGS_VIEW_WHITELIST = ['/login', '/init']

export function getRemovedCacheKeys(beforeViews: TagView[], nextViews: TagView[]) {
  const nextKeys = new Set(nextViews.map((view) => view.cacheKey))
  return beforeViews
    .filter((view) => view.closable !== false && !nextKeys.has(view.cacheKey))
    .map((view) => view.cacheKey)
}

export function clampContextMenuPosition(
  clientX: number,
  clientY: number,
  menuWidth: number,
  menuHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): { left: number; top: number } {
  const left = clientX + menuWidth > viewportWidth
    ? viewportWidth - menuWidth - 8
    : clientX
  const top = clientY + menuHeight > viewportHeight
    ? viewportHeight - menuHeight - 8
    : clientY
  return {
    left: Math.max(0, left),
    top: Math.max(0, top),
  }
}
