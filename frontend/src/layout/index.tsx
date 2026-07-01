import { useEffect } from 'react'
import { Layout } from 'antd'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { useAppStore } from '@/stores/useAppStore'
import { useSettingsStore } from '@/stores/useSettingsStore'
import Sidebar from './components/Sidebar'
import Navbar from './components/Navbar'
import TabsView from './components/TabsView'
import AppMain from './components/AppMain'
import Settings from './components/Settings'
import styles from './index.module.less'

/**
 * Root layout for authenticated pages.
 *
 * Composes Sidebar + Navbar + TabsView + AppMain + Settings,
 * with responsive behaviour driven by useBreakpoint.
 */
export default function AppLayout() {
  const { isMobile } = useBreakpoint()
  const setDevice = useAppStore((s) => s.setDevice)
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed)
  const fixedHeader = useSettingsStore((s) => s.fixedHeader)

  // Sync device type into store
  useEffect(() => {
    setDevice(isMobile ? 'mobile' : 'desktop')
    // Auto-collapse sidebar on mobile
    if (isMobile) {
      setSidebarCollapsed(true)
    }
  }, [isMobile, setDevice, setSidebarCollapsed])

  return (
    <Layout className={styles.layout}>
      <Sidebar />
      <Layout>
        {fixedHeader && <div style={{ height: 'var(--navbar-height)' }} />}
        <Navbar />
        <TabsView />
        <AppMain />
      </Layout>
      <Settings />
    </Layout>
  )
}
