import { Button, Card, Descriptions, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useParams } from '@tanstack/react-router'
import type { ScrapingTaskItem } from '@/api/scraping/scrapingTasks'
import { useScrapingTaskDetail } from './hooks/useScrapingTasks'
import { ITEM_STATUS_COLOR, ITEM_STATUS_TEXT, TASK_STATUS_COLOR, TASK_STATUS_TEXT } from './utils/status'

export default function TaskDetailPage() {
  const { id } = useParams({ strict: false }) as { id: string }
  const detail = useScrapingTaskDetail(id)
  const task = detail.task

  const columns: ColumnsType<ScrapingTaskItem> = [
    { title: '番号', dataIndex: 'movie_code', key: 'movie_code', width: 140 },
    { title: '标题', dataIndex: 'movie_title', key: 'movie_title', ellipsis: true },
    {
      title: '结果',
      key: 'status',
      width: 100,
      render: (_: unknown, record) => (
        <Tag color={ITEM_STATUS_COLOR[record.status]}>{ITEM_STATUS_TEXT[record.status] ?? record.status}</Tag>
      ),
    },
    { title: '来源', dataIndex: 'source', key: 'source', width: 100 },
    { title: '文件夹', dataIndex: 'folder', key: 'folder', ellipsis: true },
    { title: '耗时', key: 'duration', width: 100, render: (_: unknown, record) => `${record.duration_ms} ms` },
    { title: '错误', dataIndex: 'error_message', key: 'error_message', ellipsis: true },
  ]

  if (!task) {
    return <Card loading={detail.loading} />
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Card
        title="刮削任务"
        extra={(
          <Space>
            {['queued', 'running'].includes(task.status) && (
              <Button danger onClick={() => void detail.cancel()}>取消任务</Button>
            )}
            {['failed', 'partial_failed', 'cancelled'].includes(task.status) && (
              <Button onClick={() => void detail.retry()}>重试失败项</Button>
            )}
          </Space>
        )}
      >
        <Descriptions column={4}>
          <Descriptions.Item label="状态">
            <Tag color={TASK_STATUS_COLOR[task.status]}>{TASK_STATUS_TEXT[task.status] ?? task.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="总数">{task.total_count}</Descriptions.Item>
          <Descriptions.Item label="成功">{task.success_count}</Descriptions.Item>
          <Descriptions.Item label="失败/跳过">{task.failed_count}/{task.skipped_count}</Descriptions.Item>
          {task.error_message && <Descriptions.Item label="错误">{task.error_message}</Descriptions.Item>}
        </Descriptions>
      </Card>
      <Table<ScrapingTaskItem>
        rowKey="id"
        loading={detail.loading}
        dataSource={task.items}
        columns={columns}
        pagination={false}
      />
    </Space>
  )
}
