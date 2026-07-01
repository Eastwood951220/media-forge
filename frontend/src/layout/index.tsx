import { useState } from 'react'
import { Outlet } from '@tanstack/react-router'
import { Layout } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import { LayoutHeader } from './Header'
import { SideMenu } from './Sidebar'
import { TagsView } from './TagsView'
import styles from './index.module.less'

const { Content } = Layout

export default function AppLayout() {
  const darkMode = useThemeStore((state) => state.darkMode)
  const [collapsed, setCollapsed] = useState(false)

  return (
    <Layout className={darkMode ? `${styles.layout} ${styles.dark}` : styles.layout}>
      <SideMenu collapsed={collapsed} />

      <Layout className={styles.main}>
        <LayoutHeader
          darkMode={darkMode}
          collapsed={collapsed}
          onCollapse={setCollapsed}
        />
        <TagsView darkMode={darkMode} />

        <Content className={styles.content}>
          <div className={styles.pageContainer}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
