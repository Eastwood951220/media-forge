import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Space, Tag } from 'antd'
import type { CrawlRun } from '@/api/crawlerRun/types'
import { runDetailStatusLabels } from '../utils/status'

interface RunSummaryCardProps {
  run: CrawlRun | null
  actionLoading: 'stop' | 'restart' | 'retry' | null
  onStop: () => void
  onRestart: () => void
}

const crawlModeLabels: Record<string, { text: string; color: string }> = {
  incremental: { text: '增量', color: 'blue' },
  full: { text: '全量', color: 'purple' },
  temporary: { text: '临时', color: 'orange' },
}

function RunSummaryCard({ run, actionLoading, onStop, onRestart }: RunSummaryCardProps) {
  if (!run) return null

  const { text: statusText, color: statusColor } = runDetailStatusLabels[run.status] || { text: run.status, color: 'default' }
  const mode = crawlModeLabels[run.crawl_mode] || { text: run.crawl_mode, color: 'default' }

  return (
    <Card
      title={
        <Space size="middle">
          <span style={{ fontWeight: 600, fontSize: 16 }}>运行详情</span>
          <Tag color="default" style={{ fontSize: 13, padding: '2px 12px' }}>
            {run.task_name}
          </Tag>
        </Space>
      }
      extra={
        <Space>
          {(run.status === 'queued' || run.status === 'running') && (
            <Button
              danger
              icon={<StopOutlined />}
              loading={actionLoading === 'stop'}
              onClick={() => void onStop()}
            >
              停止
            </Button>
          )}
          {(run.status === 'stopped' || run.status === 'failed') && (
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
      }
      style={{
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
      }}
    >
      <Descriptions
        column={3}
        styles={{
          label: {
            fontWeight: 500,
            color: 'var(--text-secondary, #6b7280)',
            fontSize: 13,
          },
          content: {
            fontSize: 14,
          },
        }}
      >
        <Descriptions.Item label="状态">
          <Tag
            color={statusColor}
            style={{
              animation: run.status === 'running' ? 'statusPulse 2s ease-in-out infinite' : undefined,
              padding: '2px 12px',
            }}
          >
            {statusText}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="模式">
          <Tag color={mode.color}>{mode.text}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {new Date(run.created_at).toLocaleString()}
        </Descriptions.Item>
        {run.started_at && (
          <Descriptions.Item label="开始时间">
            {new Date(run.started_at).toLocaleString()}
          </Descriptions.Item>
        )}
        {run.finished_at && (
          <Descriptions.Item label="完成时间">
            {new Date(run.finished_at).toLocaleString()}
          </Descriptions.Item>
        )}
        {run.error && (
          <Descriptions.Item label="错误" span={3}>
            <span style={{ color: '#dc2626' }}>{run.error}</span>
          </Descriptions.Item>
        )}
      </Descriptions>
    </Card>
  )
}

export default RunSummaryCard
