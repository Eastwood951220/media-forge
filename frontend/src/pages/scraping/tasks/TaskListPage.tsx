import { ReloadOutlined } from '@ant-design/icons'
import { Button, Card, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from '@tanstack/react-router'
import type { ScrapingTask } from '@/api/scraping/scrapingTasks'
import { useScrapingTaskList } from './hooks/useScrapingTasks'
import { TASK_STATUS_COLOR, TASK_STATUS_TEXT } from './utils/status'

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : '-'
}

export default function TaskListPage() {
  const navigate = useNavigate()
  const list = useScrapingTaskList()

  const columns: ColumnsType<ScrapingTask> = [
    {
      title: '状态',
      key: 'status',
      width: 110,
      render: (_: unknown, record) => (
        <Tag color={TASK_STATUS_COLOR[record.status]}>{TASK_STATUS_TEXT[record.status] ?? record.status}</Tag>
      ),
    },
    {
      title: '进度',
      key: 'progress',
      width: 200,
      render: (_: unknown, record) => (
        <span>
          {record.success_count}/{record.total_count} 成功，失败 {record.failed_count}，跳过 {record.skipped_count}
        </span>
      ),
    },
    { title: '创建时间', key: 'created_at', width: 180, render: (_: unknown, record) => formatTime(record.created_at) },
    { title: '开始时间', key: 'started_at', width: 180, render: (_: unknown, record) => formatTime(record.started_at) },
    { title: '结束时间', key: 'finished_at', width: 180, render: (_: unknown, record) => formatTime(record.finished_at) },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: unknown, record) => (
        <Space>
          <Button size="small" onClick={() => void navigate({ to: '/scraping/tasks/$id', params: { id: record.id } })}>
            详情
          </Button>
          {['queued', 'running'].includes(record.status) && (
            <Button size="small" danger onClick={() => void list.cancel(record.id)}>取消</Button>
          )}
          {['failed', 'partial_failed', 'cancelled'].includes(record.status) && (
            <Button size="small" onClick={() => void list.retry(record.id)}>重试</Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="刮削任务"
      extra={(
        <Button icon={<ReloadOutlined />} onClick={() => list.refresh()}>
          刷新
        </Button>
      )}
    >
      <Table<ScrapingTask>
        rowKey="id"
        loading={list.loading}
        dataSource={list.tasks}
        columns={columns}
        pagination={{
          current: list.page,
          pageSize: list.size,
          total: list.total,
          onChange: (page, size) => {
            list.setPage(page)
            list.setSize(size)
          },
        }}
      />
    </Card>
  )
}
