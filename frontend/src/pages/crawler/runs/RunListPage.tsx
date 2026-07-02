import { useEffect, useState } from 'react'
import { Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getCrawlerRuns } from '@/api/crawlerRun'
import type { CrawlRun } from '@/api/crawlerRun/types'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

function RunListPage() {
  const [runs, setRuns] = useState<CrawlRun[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)

  useEffect(() => {
    const fetchRuns = async () => {
      setLoading(true)
      try {
        const skip = (current - 1) * 20
        const data = await getCrawlerRuns({ skip, limit: 20 })
        setRuns(data.rows)
        setTotal(data.total)
      } finally {
        setLoading(false)
      }
    }
    void fetchRuns()
  }, [current])

  const columns: ColumnsType<CrawlRun> = [
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const { text, color } = statusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '模式',
      dataIndex: 'crawl_mode',
      key: 'crawl_mode',
      render: (mode: string) => (mode === 'incremental' ? '增量' : '全量'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time: string) => new Date(time).toLocaleString(),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <h1>运行记录</h1>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={runs}
        loading={loading}
        pagination={{
          current,
          total,
          pageSize: 20,
          onChange: setCurrent,
        }}
      />
    </div>
  )
}

export default RunListPage
