import { Spin } from 'antd'

/** Shown while a route's page chunk is still downloading. */
export function RoutePending() {
  return (
    <div className="app-loading">
      <Spin size="large" />
    </div>
  )
}
