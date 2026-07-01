import { useNavigate } from '@tanstack/react-router'
import { LogoutOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Button, Layout, Space } from 'antd'
import { ThemeModeToggle } from '@/components/ThemeModeToggle'
import { useAuthStore } from '@/stores/useAuthStore'
import styles from './Header.module.less'

const { Header } = Layout

type LayoutHeaderProps = {
  darkMode?: boolean
  collapsed?: boolean
  onCollapse?: (collapsed: boolean) => void
}

export function LayoutHeader({ darkMode, collapsed, onCollapse }: LayoutHeaderProps) {
  const navigate = useNavigate()
  const userInfo = useAuthStore((state) => state.userInfo)
  const logout = useAuthStore((state) => state.logout)
  const displayName = userInfo?.displayName || userInfo?.username || 'Admin'

  const handleLogout = () => {
    logout()
    void navigate({ to: '/login', search: { redirect: undefined }, replace: true })
  }

  return (
    <Header className={darkMode ? `${styles.header} ${styles.dark}` : styles.header}>
      <div className={styles.left}>
        <button
          type="button"
          className={styles.collapseBtn}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          onClick={() => onCollapse?.(!collapsed)}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </button>
      </div>

      <Space size={12} className={styles.right}>
        <ThemeModeToggle size="middle" variant="header" />
        <div className={styles.user}>
          <span className={styles.avatar}>
            {displayName.slice(0, 1).toUpperCase()}
          </span>
          <span className={styles.userName}>{displayName}</span>
        </div>
        <Button
          aria-label="退出登录"
          title="退出登录"
          shape="circle"
          icon={<LogoutOutlined />}
          onClick={handleLogout}
        />
      </Space>
    </Header>
  )
}
