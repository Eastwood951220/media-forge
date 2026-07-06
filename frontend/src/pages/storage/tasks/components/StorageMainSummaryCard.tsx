import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Space, Tag } from 'antd'
import type { StorageMainTask } from '@/api/storage/storageTasks/types'
import { modeLabels, statusLabels } from '../utils/status'

interface StorageMainSummaryCardProps {
  task: StorageMainTask | null
  loading: boolean
  actionLoading: 'stop' | 'restart' | null
  onStop: () => void
  onRestart: () => void
}

export function StorageMainSummaryCard({
  task,
  loading,
  actionLoading,
  onStop,
  onRestart,
}: StorageMainSummaryCardProps) {
  if (!task) return null

  return (
    <Card
      title={`存储任务详情 - ${task.alias || task.id}`}
      extra={(
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
      )}
      style={{ marginBottom: 16 }}
      loading={loading}
    >
      <Descriptions column={3}>
        <Descriptions.Item label="别名">{task.alias || '-'}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusLabels[task.status]?.color}>{statusLabels[task.status]?.text || task.status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="模式">{modeLabels[task.storage_mode] || task.storage_mode}</Descriptions.Item>
        <Descriptions.Item label="总数">{task.total_count}</Descriptions.Item>
        <Descriptions.Item label="成功">
          <span style={{ color: '#52c41a' }}>{task.success_count}</span>
        </Descriptions.Item>
        <Descriptions.Item label="失败">
          {task.failed_count > 0 ? (
            <span style={{ color: '#ff4d4f' }}>{task.failed_count}</span>
          ) : (
            task.failed_count
          )}
        </Descriptions.Item>
        <Descriptions.Item label="跳过">{task.skipped_count}</Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {task.created_at ? new Date(task.created_at).toLocaleString() : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="完成时间">
          {task.finished_at ? new Date(task.finished_at).toLocaleString() : '-'}
        </Descriptions.Item>
        {task.error_message && (
          <Descriptions.Item label="错误信息" span={3}>
            {task.error_message}
          </Descriptions.Item>
        )}
      </Descriptions>
    </Card>
  )
}
