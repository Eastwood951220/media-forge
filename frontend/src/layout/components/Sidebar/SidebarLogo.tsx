import { useSettingsStore } from '@/stores/useSettingsStore'
import styles from './index.module.less'

type SidebarLogoProps = {
  collapsed?: boolean
}

function SidebarLogo({ collapsed = false }: SidebarLogoProps) {
  const showSidebarLogo = useSettingsStore((state) => state.showSidebarLogo)

  if (!showSidebarLogo) {
    return null
  }

  return (
    <div className={styles.logo}>
      <span
        className={`${styles.logoText} ${collapsed ? styles.logoTextCollapsed : ''}`}
      >
        Media Forge
      </span>
    </div>
  )
}

export default SidebarLogo
