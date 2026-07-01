import { createRootRoute, Outlet } from '@tanstack/react-router'
import { ConfigProvider, App as AntApp, Typography } from 'antd'

const { Title } = Typography

export const Route = createRootRoute({
  component: () => (
    <ConfigProvider>
      <AntApp>
        <div className="p-8">
          <Title level={1}>Media Forge 🎬</Title>
          <Outlet />
        </div>
      </AntApp>
    </ConfigProvider>
  ),
})
