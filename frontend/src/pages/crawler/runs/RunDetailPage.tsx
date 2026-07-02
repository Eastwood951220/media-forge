import { useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { Card, Descriptions, Input, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getCrawlerRun, getCrawlerRunTasks } from '@/api/crawlerRun'
import type { CrawlRun, CrawlRunDetailTask } from '@/api/crawlerRun/types'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
  pending_crawl: { text: '待爬取', color: 'default' },
  crawled: { text: '已爬取', color: 'processing' },
  crawl_failed: { text: '爬取失败', color: 'error' },
  saved: { text: '已保存', color: 'success' },
  save_failed: { text: '保存失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

function RunDetailPage() {
  const { id } = useParams({ strict: false })
  const [run, setRun] = useState<CrawlRun | null>(null)
  const [tasks, setTasks] = useState<CrawlRunDetailTask[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    if (!id) return
    const fetchRun = async () => {
      const data = await getCrawlerRun(id)
      setRun(data)
    }
    void fetchRun()
  }, [id])

  useEffect(() => {
    if (!id) return
    const fetchTasks = async () => {
      setLoading(true)
      try {
        const data = await getCrawlerRunTasks(id, {
          limit: 200,
          status: statusFilter,
          keyword: keyword || undefined,
        })
        setTasks(data.rows)
      } finally {
        setLoading(false)
      }
    }
    void fetchTasks()
  }, [id, statusFilter, keyword])

  const columns: ColumnsType<CrawlRunDetailTask> = [
    {
      title: '番号',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '来源',
      dataIndex: 'source_name',
      key: 'source_name',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const { text, color } = statusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      ellipsis: true,
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      {run && (
        <Card title={`运行详情 - ${run.task_name}`} style={{ marginBottom: 16 }}>
          <Descriptions column={3}>
            <Descriptions.Item label="状态">
              <Tag color={statusLabels[run.status]?.color}>{statusLabels[run.status]?.text}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="模式">{run.crawl_mode === 'incremental' ? '增量' : '全量'}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{new Date(run.created_at).toLocaleString()}</Descriptions.Item>
            {run.error && <Descriptions.Item label="错误" span={3}>{run.error}</Descriptions.Item>}
          </Descriptions>
        </Card>
      )}

      <Card title="子任务列表">
        <Space style={{ marginBottom: 16 }}>
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 120 }}
            onChange={(value) => setStatusFilter(value)}
            options={Object.entries(statusLabels).map(([key, { text }]) => ({
              value: key,
              label: text,
            }))}
          />
          <Input.Search
            placeholder="搜索番号或名称"
            allowClear
            onSearch={(value) => setKeyword(value)}
            style={{ width: 200 }}
          />
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={tasks}
          loading={loading}
          pagination={{ pageSize: 50 }}
        />
      </Card>
    </div>
  )
}

export default RunDetailPage
