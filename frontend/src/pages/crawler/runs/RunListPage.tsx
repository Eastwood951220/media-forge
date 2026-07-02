import { useCallback, useEffect, useState } from 'react'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Space, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getCrawlerRuns, restartCrawlerRun, stopCrawlerRun } from '@/api/crawlerRun'
import type { CrawlRun } from '@/api/crawlerRun/types'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

const PAGE_SIZE = 20

function RunListPage() {
  const [runs, setRuns] = useState<CrawlRun[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)

  const fetchRuns = useCallback(async (page: number) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const data = await getCrawlerRuns({ skip, limit: PAGE_SIZE })
      setRuns(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchRuns(current)
  }, [current, fetchRuns])

  const handleStop = useCallback(async (run: CrawlRun) => {
    try {
      await stopCrawlerRun(run.id)
      message.success('已停止运行')
      void fetchRuns(current)
    } catch {
      message.error('停止失败')
    }
  }, [current, fetchRuns])

  const handleRestart = useCallback(async (run: CrawlRun) => {
    try {
      await restartCrawlerRun(run.id)
      message.success('已重启运行')
      void fetchRuns(current)
    } catch {
      message.error('重启失败')
    }
  }, [current, fetchRuns])

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
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          {(record.status === 'queued' || record.status === 'running') && (
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => handleStop(record)}
            >
              停止
            </Button>
          )}
          {(record.status === 'stopped' || record.status === 'failed') && (
            <Button
              size="small"
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => handleRestart(record)}
            >
              重启
            </Button>
          )}
        </Space>
      ),
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
          pageSize: PAGE_SIZE,
          onChange: setCurrent,
        }}
      />
    </div>
  )
}

export default RunListPage
