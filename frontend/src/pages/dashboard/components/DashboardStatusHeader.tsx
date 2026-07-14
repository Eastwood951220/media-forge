import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Button, Tag } from 'antd'
import type { SystemStatus } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusMeta: Record<SystemStatus, { label: string; color: string; icon: React.ReactNode }> = {
  healthy: { label: '健康', color: 'success', icon: <CheckCircleOutlined /> },
  busy: { label: '运行中', color: 'processing', icon: <SyncOutlined spin /> },
  warning: { label: '需要关注', color: 'warning', icon: <WarningOutlined /> },
  error: { label: '异常', color: 'error', icon: <CloseCircleOutlined /> },
}

interface Props {
  status: SystemStatus
  refreshedAt: string
  refreshing: boolean
  onRefresh: () => void
}

export function DashboardStatusHeader({ status, refreshedAt, refreshing, onRefresh }: Props) {
  const meta = statusMeta[status]
  return (
    <section className={styles.statusHeader}>
      <div>
        <p className={styles.eyebrow}>Media Forge</p>
        <h1>运行态总览</h1>
        <p className={styles.headerSummary}>采集、影片库、存储任务与索引状态的实时概览。</p>
      </div>
      <div className={styles.headerActions}>
        <Tag color={meta.color} icon={meta.icon}>{meta.label}</Tag>
        <span className={styles.refreshedAt}>刷新于 {new Date(refreshedAt).toLocaleString()}</span>
        <Button icon={<ReloadOutlined />} loading={refreshing} onClick={onRefresh}>刷新</Button>
      </div>
    </section>
  )
}
