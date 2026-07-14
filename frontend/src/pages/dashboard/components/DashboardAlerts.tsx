import { Link } from '@tanstack/react-router'
import { Empty, Tag } from 'antd'
import type { DashboardAlert } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

export function DashboardAlerts({ alerts }: { alerts: DashboardAlert[] }) {
  return (
    <article className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>需要关注</h2>
      </div>
      {alerts.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无需要关注的问题" />
      ) : (
        <div className={styles.alertList}>
          {alerts.map((alert) => (
            <div className={styles.alertRow} key={alert.id}>
              <Tag color={alert.severity === 'error' ? 'error' : 'warning'}>{alert.source}</Tag>
              <div>
                {alert.target_path ? <Link to={alert.target_path}>{alert.title}</Link> : <strong>{alert.title}</strong>}
                <span>{alert.description}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}
