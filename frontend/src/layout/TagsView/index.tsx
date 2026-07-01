import { useRouterState } from '@tanstack/react-router'
import styles from './TagsView.module.less'

type TagsViewProps = {
  darkMode?: boolean
}

export function TagsView({ darkMode }: TagsViewProps) {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const isDashboard = pathname === '/'

  return (
    <div className={darkMode ? `${styles.tagsView} ${styles.dark}` : styles.tagsView}>
      <div className={styles.scrollContent}>
        <div className={styles.tagsInner}>
          <span className={`${styles.tag} ${isDashboard ? styles.active : ''} ${styles.affix}`}>
            {isDashboard ? <span className={styles.dot} /> : null}
            <span className={styles.tagTitle}>仪表盘</span>
          </span>
        </div>
      </div>
    </div>
  )
}
