import { Outlet } from '@tanstack/react-router'
import { Layout } from 'antd'
import { useSettingsStore } from '@/stores/useSettingsStore'
import { useMobile } from '@/hooks/useBreakpoint'
import styles from './index.module.less'

const { Content } = Layout

export default function AppMain() {
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)
  const showTagsView = useSettingsStore((s) => s.showTagsView)
  const isMobile = useMobile()

  const className = [
    styles['app-main'],
    fixedHeader && styles['app-main--fixed-header'],
    fixedHeader && showTagsView && styles['app-main--fixed-header-with-tags'],
    isMobile && styles['app-main--mobile'],
    'content-area',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <Content className={className}>
      <Outlet />
    </Content>
  )
}
