import { createRootRoute, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp } from 'antd'

export const Route = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <Outlet />
      </AntApp>
    </ConfigProvider>
  ),
})
