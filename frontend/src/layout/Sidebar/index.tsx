import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { DashboardOutlined } from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import type { MenuProps } from 'antd'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './Sidebar.module.less'

const { Sider } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
]

type SideMenuProps = {
  collapsed: boolean
}

export function SideMenu({ collapsed }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const selectedKeys = useMemo(() => [pathname === '/' ? '/' : pathname], [pathname])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    if (nextPath !== pathname) {
      void navigate({ to: nextPath })
    }
  }

  return (
    <Sider
      collapsed={collapsed}
      width={232}
      collapsedWidth={80}
      collapsible={false}
      className={[
        styles.sider,
        darkMode ? styles.dark : '',
        collapsed ? styles.collapsed : '',
      ].filter(Boolean).join(' ')}
    >
      <div className={styles.logo}>
        <span className={styles.logoMark}>MF</span>
        {!collapsed && <span className={styles.logoText}>Media Forge</span>}
      </div>

      <div className={styles.menuWrapper}>
        <Menu
          className={styles.menu}
          mode="inline"
          theme={darkMode ? 'dark' : 'light'}
          inlineCollapsed={collapsed}
          selectedKeys={selectedKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Sider>
  )
}
