import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Descriptions, Progress, Space, Statistic, Tag, Typography } from 'antd'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'
import styles from '../StorageTasks.module.less'
import { modeLabels, statusLabels } from '../utils/status'

interface StorageMainSummaryCardProps {
  task: StorageMainTask | null
  loading: boolean
  actionLoading: 'stop' | 'restart' | null
  onStop: () => void
  onRestart: () => void
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '-'
}

function getProgressPercent(task: StorageMainTask) {
  if (!task.total_count) return 0
  const finished = task.success_count + task.failed_count + task.skipped_count
  return Math.min(100, Math.round((finished / task.total_count) * 100))
}

export function StorageMainSummaryCard({
  task,
  loading,
  actionLoading,
  onStop,
  onRestart,
}: StorageMainSummaryCardProps) {
  if (!task) return null

  const status = statusLabels[task.status] || { text: task.status, color: 'default' }
  const progressPercent = getProgressPercent(task)

  return (
    <Card
      className={styles.summaryCard}
      loading={loading}
      title={(
        <div className={styles.summaryTitle}>
          <div className={styles.summaryHeading}>
            <Typography.Title level={4}>{task.alias || task.id}</Typography.Title>
            <Space size={8} wrap>
              <Tag>{modeLabels[task.storage_mode] || task.storage_mode}</Tag>
              <Tag color={status.color}>{status.text}</Tag>
            </Space>
          </div>
          <Space>
            {(task.status === 'queued' || task.status === 'running') && (
              <Button
                danger
                icon={<StopOutlined />}
                loading={actionLoading === 'stop'}
                onClick={() => void onStop()}
              >
                停止
              </Button>
            )}
            {(task.status === 'stopped' || task.status === 'failed') && (
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={actionLoading === 'restart'}
                onClick={() => void onRestart()}
              >
                重启
              </Button>
            )}
          </Space>
        </div>
      )}
    >
      <div className={styles.summaryGrid}>
        <section className={styles.progressPanel}>
          <div className={styles.panelLabel}>任务进度</div>
          <Progress
            percent={progressPercent}
            status={task.failed_count > 0 ? 'exception' : undefined}
            strokeColor={task.failed_count > 0 ? undefined : '#1677ff'}
          />
          <div className={styles.progressMeta}>
            <span>总数 {task.total_count}</span>
            <span>已处理 {task.success_count + task.failed_count + task.skipped_count}</span>
          </div>
        </section>

        <div className={styles.metricGrid}>
          <Statistic title="成功" value={task.success_count} valueStyle={{ color: '#389e0d' }} />
          <Statistic title="失败" value={task.failed_count} valueStyle={{ color: task.failed_count > 0 ? '#cf1322' : undefined }} />
          <Statistic title="跳过" value={task.skipped_count} />
        </div>
      </div>

      <Descriptions className={styles.summaryDescriptions} column={{ xs: 1, sm: 2, lg: 3 }} size="small">
        <Descriptions.Item label="任务编号">{task.id}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatDateTime(task.created_at)}</Descriptions.Item>
        <Descriptions.Item label="完成时间">{formatDateTime(task.finished_at)}</Descriptions.Item>
      </Descriptions>

      {task.error_message && (
        <Alert className={styles.summaryError} type="error" showIcon message="错误信息" description={task.error_message} />
      )}
    </Card>
  )
}
