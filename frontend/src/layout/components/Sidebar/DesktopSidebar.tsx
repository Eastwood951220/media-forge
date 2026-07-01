import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useAppStore } from '@/stores/useAppStore'
import SidebarLogo from './SidebarLogo'
import styles from './index.module.less'

const { Sider } = Layout

const menuItems: MenuProps['items'] = [
  {
    key: 'dashboard',
    icon: <DashboardOutlined />,
    label: 'Dashboard',
  },
  {
    key: 'user',
    icon: <UserOutlined />,
    label: 'User',
  },
  {
    key: 'settings',
    icon: <SettingOutlined />,
    label: 'Settings',
  },
]

function DesktopSidebar() {
  const collapsed = useAppStore((state) => state.sidebarCollapsed)

  return (
    <Sider
      className={styles.sidebar}
      collapsible
      collapsed={collapsed}
      collapsedWidth={64}
      width={210}
      trigger={null}
    >
      <SidebarLogo collapsed={collapsed} />
      <div className={styles.menuWrap}>
        <Menu
          theme="dark"
          mode="inline"
          defaultSelectedKeys={['dashboard']}
          items={menuItems}
        />
      </div>
    </Sider>
  )
}

export default DesktopSidebar
