import { Classic } from '@theme-toggles/react'
import '@theme-toggles/react/styles/classic.css'
import { clsx } from 'clsx'
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
  const { runTransition, triggerRef } = useThemeViewTransition({
    toggleTheme: toggleMode,
  })

  return (
    <div className={`${styles.toggleWrap} ${styles[variant]} ${className ?? ''}`}>
      {variant === 'login' ? (
        <span className={styles.label}>
          {darkMode ? '深色模式' : '浅色模式'}
        </span>
      ) : null}
      <div ref={triggerRef} className={styles.buttonWrap}>
        <Classic
          aria-label="切换明暗模式"
          className={clsx('theme-toggle', styles.toggleButton, styles[size])}
          duration={450}
          onClick={() => {
            void runTransition()
          }}
        />
      </div>
    </div>
  )
}