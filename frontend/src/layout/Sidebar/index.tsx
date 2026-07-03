import { useMemo } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import {
  CloudOutlined,
  DashboardOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
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
  {
    key: 'crawler',
    icon: <SearchOutlined />,
    label: '爬虫',
    children: [
      {
        key: '/crawler/tasks',
        icon: <UnorderedListOutlined />,
        label: '任务列表',
      },
      {
        key: '/crawler/runs',
        icon: <HistoryOutlined />,
        label: '运行记录',
      },
      {
        key: '/crawler/config',
        icon: <SettingOutlined />,
        label: '爬虫配置',
      },
    ],
  },
  {
    key: 'storage',
    icon: <CloudOutlined />,
    label: '存储',
    children: [
      {
        key: '/storage/tasks',
        icon: <HistoryOutlined />,
        label: '存储任务',
      },
      {
        key: '/storage/config',
        icon: <SettingOutlined />,
        label: '存储配置',
      },
    ],
  },
  {
    key: 'content',
    icon: <PlayCircleOutlined />,
    label: '内容管理',
    children: [
      {
        key: '/content/movies',
        icon: <VideoCameraOutlined />,
        label: '电影列表',
      },
    ],
  },
]

type SideMenuProps = {
  collapsed: boolean
}

export function SideMenu({ collapsed }: SideMenuProps) {
  const navigate = useNavigate()
  const darkMode = useThemeStore((state) => state.darkMode)
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const selectedKey = pathname.startsWith('/crawler/tasks')
    ? '/crawler/tasks'
    : pathname.startsWith('/crawler/runs')
      ? '/crawler/runs'
      : pathname.startsWith('/crawler/config')
        ? '/crawler/config'
        : pathname.startsWith('/storage/tasks')
          ? '/storage/tasks'
          : pathname.startsWith('/storage/config')
            ? '/storage/config'
            : pathname.startsWith('/content/movies')
              ? '/content/movies'
              : pathname
  const selectedKeys = useMemo(() => [selectedKey === '/' ? '/' : selectedKey], [selectedKey])
  const openKeys = useMemo(() => {
    const keys: string[] = []
    if (pathname.startsWith('/crawler')) keys.push('crawler')
    if (pathname.startsWith('/storage')) keys.push('storage')
    if (pathname.startsWith('/content')) keys.push('content')
    return keys
  }, [pathname])

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    const nextPath = String(key)
    if (nextPath.startsWith('/') && nextPath !== pathname) {
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
          defaultOpenKeys={openKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </Sider>
  )
}
