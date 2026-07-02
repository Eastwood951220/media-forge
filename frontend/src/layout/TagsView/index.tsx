import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import {
  CloseCircleOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import { getFullPath, getRouteTagMeta } from '@/routes/tags'
import type { RouteCacheControl } from '@/layout/routeCache'
import { useRouteCacheControl } from '@/layout/routeCache'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import type { TagView } from '@/stores/useTagsViewStore'
import styles from './TagsView.module.less'

/** TagsView 白名单 - 这些路径不会显示在标签页中 */
const TAGS_VIEW_WHITELIST = ['/login', '/init']

type TagsViewProps = {
  darkMode?: boolean
  cacheControl?: RouteCacheControl
}

type ContextMenuState = {
  visible: boolean
  left: number
  top: number
  selectedTag?: TagView
}

function getRemovedCacheKeys(beforeViews: TagView[], nextViews: TagView[]) {
  const nextKeys = new Set(nextViews.map((view) => view.fullPath))
  return beforeViews
    .filter((view) => view.closable !== false && !nextKeys.has(view.fullPath))
    .map((view) => view.fullPath)
}

export function TagsView({ darkMode, cacheControl: cacheControlProp }: TagsViewProps) {
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const visitedViews = useTagsViewStore((state) => state.visitedViews)
  const addVisitedView = useTagsViewStore((state) => state.addVisitedView)
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const removeOtherViews = useTagsViewStore((state) => state.removeOtherViews)
  const removeLeftViews = useTagsViewStore((state) => state.removeLeftViews)
  const removeRightViews = useTagsViewStore((state) => state.removeRightViews)
  const removeAllViews = useTagsViewStore((state) => state.removeAllViews)
  const routeCacheControl = useRouteCacheControl()
  const cacheControl = cacheControlProp ?? routeCacheControl
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    left: 0,
    top: 0,
  })

  const fullPath = getFullPath(pathname, searchStr)
  const currentMeta = useMemo(() => getRouteTagMeta(pathname), [pathname])
  const isActive = useCallback((view: TagView) => view.fullPath === fullPath, [fullPath])

  useEffect(() => {
    // 白名单中的路径不添加到标签页
    if (TAGS_VIEW_WHITELIST.includes(pathname)) {
      return
    }

    addVisitedView({
      path: pathname,
      fullPath,
      title: currentMeta.title,
      closable: pathname !== '/' && !currentMeta.affix,
      query: searchStr ? Object.fromEntries(new URLSearchParams(searchStr)) : undefined,
    })
  }, [addVisitedView, currentMeta, fullPath, pathname, searchStr])

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => (prev.visible ? { ...prev, visible: false } : prev))
  }, [])

  useEffect(() => {
    document.addEventListener('click', closeContextMenu)
    return () => document.removeEventListener('click', closeContextMenu)
  }, [closeContextMenu])

  const navigateAfterClose = useCallback(
    (views: TagView[]) => {
      if (views.some((view) => view.fullPath === fullPath)) return
      const last = views.at(-1)
      void navigate({ to: last?.fullPath ?? '/' })
    },
    [fullPath, navigate],
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
      void cacheControl.destroy(tag.fullPath)
      navigateAfterClose(nextViews)
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleMouseDown = useCallback(
    (tag: TagView, event: React.MouseEvent) => {
      if (event.button === 1 && tag.closable !== false) {
        event.preventDefault()
        const nextViews = removeSelectedView(tag)
        void cacheControl.destroy(tag.fullPath)
        navigateAfterClose(nextViews)
      }
    },
    [cacheControl, navigateAfterClose, removeSelectedView],
  )

  const handleContextMenu = useCallback((tag: TagView, event: React.MouseEvent) => {
    event.preventDefault()
    const menuWidth = 140
    const menuHeight = 260
    const left = event.clientX + menuWidth > window.innerWidth
      ? window.innerWidth - menuWidth - 8
      : event.clientX
    const top = event.clientY + menuHeight > window.innerHeight
      ? window.innerHeight - menuHeight - 8
      : event.clientY

    setContextMenu({
      visible: true,
      left: Math.max(0, left),
      top: Math.max(0, top),
      selectedTag: tag,
    })
  }, [])

  const handleRefresh = useCallback(() => {
    closeContextMenu()
    cacheControl.refresh(contextMenu.selectedTag?.fullPath ?? fullPath)
    void navigate({ to: fullPath, replace: true })
  }, [cacheControl, closeContextMenu, contextMenu.selectedTag, fullPath, navigate])

  const handleCloseCurrent = useCallback(() => {
    closeContextMenu()
    const tag = contextMenu.selectedTag
    if (!tag || tag.closable === false) return
    const nextViews = removeSelectedView(tag)
    void cacheControl.destroy(tag.fullPath)
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

  const selectedTag = contextMenu.selectedTag
  const selectedIndex = selectedTag
    ? visitedViews.findIndex((view) => view.fullPath === selectedTag.fullPath)
    : -1
  const isFirst = selectedIndex <= 0
  const isLast = selectedIndex === visitedViews.length - 1
  const isOnly = visitedViews.filter((view) => view.closable !== false).length <= 1
  const isSelectedAffix = selectedTag?.closable === false

  return (
    <>
      <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
        <div className={styles.scrollContent}>
          <div className={styles.tagsInner}>
            {visitedViews.map((view) => (
              <span
                key={view.fullPath}
                data-path={view.path}
                data-full-path={view.fullPath}
                className={`${styles.tag} ${isActive(view) ? styles.active : ''} ${view.closable === false ? styles.affix : ''}`}
                onClick={() => void navigate({ to: view.fullPath })}
                onMouseDown={(event) => handleMouseDown(view, event)}
                onContextMenu={(event) => handleContextMenu(view, event)}
              >
                {isActive(view) ? <span className={styles.dot} /> : null}
                <span className={styles.tagTitle}>{view.title}</span>
                {view.closable !== false && (
                  <CloseOutlined
                    aria-label={`关闭 ${view.title}`}
                    className={styles.closeIcon}
                    onClick={(event) => handleClose(view, event)}
                  />
                )}
              </span>
            ))}
          </div>
        </div>
      </div>

      {contextMenu.visible && selectedTag && (
        <div
          className={styles.contextMenu}
          style={{ position: 'fixed', left: contextMenu.left, top: contextMenu.top }}
        >
          <button type="button" className={styles.menuItem} onClick={handleRefresh}>
            <ReloadOutlined /> 刷新页面
          </button>
          <div className={styles.menuDivider} />
          <button
            type="button"
            className={`${styles.menuItem} ${isSelectedAffix ? styles.disabled : ''}`}
            disabled={isSelectedAffix}
            onClick={handleCloseCurrent}
          >
            <CloseOutlined /> 关闭当前
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
            disabled={isOnly}
            onClick={handleCloseOthers}
          >
            <CloseCircleOutlined /> 关闭其他
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isFirst ? styles.disabled : ''}`}
            disabled={isFirst}
            onClick={handleCloseLeft}
          >
            <RollbackOutlined /> 关闭左侧
          </button>
          <button
            type="button"
            className={`${styles.menuItem} ${isLast ? styles.disabled : ''}`}
            disabled={isLast}
            onClick={handleCloseRight}
          >
            <RollbackOutlined className={styles.flipX} /> 关闭右侧
          </button>
          <div className={styles.menuDivider} />
          <button
            type="button"
            className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
            disabled={isOnly}
            onClick={handleCloseAll}
          >
            <CloseCircleOutlined /> 全部关闭
          </button>
        </div>
      )}
    </>
  )
}
