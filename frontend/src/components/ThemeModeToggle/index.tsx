import { BulbOutlined, MoonOutlined } from '@ant-design/icons'
import { Switch } from 'antd'
import { useThemeViewTransition } from '@/hooks/useThemeViewTransition'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './index.module.less'

export type ThemeModeToggleProps = {
  className?: string
  variant?: 'header' | 'login'
  size?: 'small' | 'middle'
}

export function ThemeModeToggle({
  className,
  variant = 'header',
  size = 'middle',
}: ThemeModeToggleProps) {
  const darkMode = useThemeStore((state) => state.darkMode)
  const toggleMode = useThemeStore((state) => state.toggleMode)
  const { runTransition, transitioning, triggerRef } = useThemeViewTransition({
    toggleTheme: toggleMode,
  })

  return (
    <div
      ref={triggerRef}
      className={`${styles.toggleWrap} ${styles[variant]} ${className ?? ''}`}
    >
      {variant === 'login' ? (
        <span className={styles.label}>
          {darkMode ? '深色模式' : '浅色模式'}
        </span>
      ) : null}
      <Switch
        aria-label="切换明暗模式"
        checked={darkMode}
        checkedChildren={<MoonOutlined />}
        disabled={transitioning}
        loading={transitioning}
        size={size}
        unCheckedChildren={<BulbOutlined />}
        onChange={runTransition}
      />
    </div>
  )
}
