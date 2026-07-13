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

const crawlModeLabels: Record<string, string> = {
  incremental: '增量',
  full: '全量',
  temporary: '临时',
}

function RunSummaryCard({ run, actionLoading, onStop, onRestart }: RunSummaryCardProps) {
  if (!run) return null

  return (
    <Card
      title={`运行详情 - ${run.task_name}`}
      extra={(
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
      )}
      style={{ marginBottom: 16 }}
    >
      <Descriptions column={3}>
        <Descriptions.Item label="状态">
          <Tag color={runDetailStatusLabels[run.status]?.color}>{runDetailStatusLabels[run.status]?.text}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="模式">{crawlModeLabels[run.crawl_mode] ?? run.crawl_mode}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{new Date(run.created_at).toLocaleString()}</Descriptions.Item>
        {run.error && <Descriptions.Item label="错误" span={3}>{run.error}</Descriptions.Item>}
      </Descriptions>
    </Card>
  )
}

export default RunSummaryCard
