import { Drawer, Menu } from 'antd'
import {
  DashboardOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useAppStore } from '@/stores/useAppStore'
import SidebarLogo from './SidebarLogo'
import styles from './index.module.less'

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

function MobileDrawer() {
  const collapsed = useAppStore((state) => state.sidebarCollapsed)
  const setSidebarCollapsed = useAppStore((state) => state.setSidebarCollapsed)

  const open = !collapsed

  const handleClose = () => {
    setSidebarCollapsed(true)
  }

  const handleMenuClick: MenuProps['onClick'] = () => {
    setSidebarCollapsed(true)
  }

  return (
    <Drawer
      className={styles.mobileDrawer}
      placement="left"
      open={open}
      width={210}
      closable={false}
      onClose={handleClose}
    >
      <SidebarLogo />
      <div className={styles.menuWrap}>
        <Menu
          theme="dark"
          mode="inline"
          defaultSelectedKeys={['dashboard']}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Drawer>
  )
}

export default MobileDrawer
