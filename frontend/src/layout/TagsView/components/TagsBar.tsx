import { CloseOutlined } from '@ant-design/icons'
import type { TagView } from '@/stores/useTagsViewStore'
import styles from '../TagsView.module.less'

type TagsBarProps = {
  darkMode?: boolean
  isActive: (view: TagView) => boolean
  onClose: (tag: TagView, event?: React.MouseEvent) => void
  onContextMenu: (tag: TagView, event: React.MouseEvent) => void
  onMouseDown: (tag: TagView, event: React.MouseEvent) => void
  onNavigate: (fullPath: string) => void
  visitedViews: TagView[]
}

export function TagsBar({
  darkMode,
  isActive,
  onClose,
  onContextMenu,
  onMouseDown,
  onNavigate,
  visitedViews,
}: TagsBarProps) {
  return (
    <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
      <div className={styles.scrollContent}>
        <div className={styles.tagsInner}>
          {visitedViews.map((view) => (
            <span
              key={view.cacheKey}
              data-path={view.path}
              data-full-path={view.fullPath}
              data-cache-key={view.cacheKey}
              className={`${styles.tag} ${isActive(view) ? styles.active : ''} ${view.closable === false ? styles.affix : ''}`}
              onClick={() => onNavigate(view.fullPath)}
              onMouseDown={(event) => onMouseDown(view, event)}
              onContextMenu={(event) => onContextMenu(view, event)}
            >
              {isActive(view) ? <span className={styles.dot} /> : null}
              <span className={styles.tagTitle}>{view.title}</span>
              {view.closable !== false && (
                <CloseOutlined
                  aria-label={`关闭 ${view.title}`}
                  className={styles.closeIcon}
                  onClick={(event) => onClose(view, event)}
                />
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
