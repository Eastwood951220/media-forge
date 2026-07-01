import { useSettingsStore } from '@/stores/useSettingsStore'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import Hamburger from './Hamburger'
import BreadcrumbNav from './Breadcrumb'
import styles from './index.module.less'

/**
 * Top navigation bar: hamburger (always), breadcrumb (desktop),
 * and a right-side slot for the theme toggle.
 *
 * When `fixedHeader` is enabled the bar is position:fixed.
 */
export default function Navbar() {
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)

  return (
    <header
      className={`${styles.navbar} ${fixedHeader ? styles.navbarFixed : ''}`}
    >
      <div className={styles.leftSection}>
        <Hamburger />
        <BreadcrumbNav />
      </div>

      <div className={styles.rightSection}>
        <ThemeModeToggle variant="header" />
      </div>
    </header>
  )
}
