import {
  CloseCircleOutlined,
  CloseOutlined,
  ReloadOutlined,
  RollbackOutlined,
} from '@ant-design/icons'
import type { TagView } from '@/stores/useTagsViewStore'
import type { ContextMenuState } from '../hooks/useTagsContextMenu'
import styles from '../TagsView.module.less'

type TagsContextMenuProps = {
  actions: {
    handleRefresh: () => void
    handleCloseCurrent: () => void
    handleCloseOthers: () => void
    handleCloseLeft: () => void
    handleCloseRight: () => void
    handleCloseAll: () => void
  }
  contextMenu: ContextMenuState
  selectedTag?: TagView
  visitedViews: TagView[]
}

export function TagsContextMenu({
  actions,
  contextMenu,
  selectedTag,
  visitedViews,
}: TagsContextMenuProps) {
  if (!contextMenu.visible || !selectedTag) return null

  const selectedIndex = selectedTag
    ? visitedViews.findIndex((view) => view.cacheKey === selectedTag.cacheKey)
    : -1
  const isFirst = selectedIndex <= 0
  const isLast = selectedIndex === visitedViews.length - 1
  const isOnly = visitedViews.filter((view) => view.closable !== false).length <= 1
  const isSelectedAffix = selectedTag?.closable === false

  return (
    <div
      className={styles.contextMenu}
      style={{ position: 'fixed', left: contextMenu.left, top: contextMenu.top }}
    >
      <button type="button" className={styles.menuItem} onClick={actions.handleRefresh}>
        <ReloadOutlined /> 刷新页面
      </button>
      <div className={styles.menuDivider} />
      <button
        type="button"
        className={`${styles.menuItem} ${isSelectedAffix ? styles.disabled : ''}`}
        disabled={isSelectedAffix}
        onClick={actions.handleCloseCurrent}
      >
        <CloseOutlined /> 关闭当前
      </button>
      <button
        type="button"
        className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
        disabled={isOnly}
        onClick={actions.handleCloseOthers}
      >
        <CloseCircleOutlined /> 关闭其他
      </button>
      <button
        type="button"
        className={`${styles.menuItem} ${isFirst ? styles.disabled : ''}`}
        disabled={isFirst}
        onClick={actions.handleCloseLeft}
      >
        <RollbackOutlined /> 关闭左侧
      </button>
      <button
        type="button"
        className={`${styles.menuItem} ${isLast ? styles.disabled : ''}`}
        disabled={isLast}
        onClick={actions.handleCloseRight}
      >
        <RollbackOutlined className={styles.flipX} /> 关闭右侧
      </button>
      <div className={styles.menuDivider} />
      <button
        type="button"
        className={`${styles.menuItem} ${isOnly ? styles.disabled : ''}`}
        disabled={isOnly}
        onClick={actions.handleCloseAll}
      >
        <CloseCircleOutlined /> 全部关闭
      </button>
    </div>
  )
}
