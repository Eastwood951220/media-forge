import { useAppStore } from '@/stores/useAppStore'
import styles from './index.module.less'

/** Three-line hamburger icon that rotates 90deg when the sidebar is collapsed. */
export default function Hamburger() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)

  return (
    <button
      aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
      className={`${styles.hamburger} ${collapsed ? styles.hamburgerCollapsed : ''}`}
      onClick={toggleSidebar}
      type="button"
    >
      <svg viewBox="0 0 1024 1024" fill="currentColor" aria-hidden="true">
        <path d="M128 256h768a42.667 42.667 0 0 0 0-85.333H128a42.667 42.667 0 1 0 0 85.333zm768 213.333H128a42.667 42.667 0 0 0 0 85.334h768a42.667 42.667 0 0 0 0-85.334zm0 298.667H128a42.667 42.667 0 0 0 0 85.333h768a42.667 42.667 0 0 0 0-85.333z" />
      </svg>
    </button>
  )
}
