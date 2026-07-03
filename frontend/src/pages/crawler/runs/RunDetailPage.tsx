import { useCallback, useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { Card, Descriptions, Input, Select, Space, Table, Tag } from 'antd'
import RunLogsTimeline from './components/RunLogsTimeline'
import type { ColumnsType } from 'antd/es/table'
import { getCrawlerRun, getCrawlerRunTasks } from '@/api/crawlerRun'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'
import { useCrawlerSSE } from '@/hooks/useCrawlerSSE'
import type { CrawlerEvent } from '@/api/crawler/sse'

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

  // Reset state when run ID changes
  useEffect(() => {
    setRun(null)
    setTasks([])
    setStatusFilter(undefined)
    setKeyword('')
  }, [id])

  // Initial fetch of run details
  useEffect(() => {
    if (!id) return
    let cancelled = false
    const fetchRun = async () => {
      const data = await getCrawlerRun(id)
      if (!cancelled) {
        setRun(data)
      }
    }
    void fetchRun()
    return () => {
      cancelled = true
    }
  }, [id])

  // Initial fetch of task list
  useEffect(() => {
    if (!id) return
    let cancelled = false
    const fetchTasks = async () => {
      setLoading(true)
      try {
        const data = await getCrawlerRunTasks(id, {
          limit: 200,
          status: statusFilter,
          keyword: keyword || undefined,
        })
        if (!cancelled) {
          setTasks(data.rows)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void fetchTasks()
    return () => {
      cancelled = true
    }
  }, [id, statusFilter, keyword])

  // SSE event handlers for real-time updates
  const handleRunStatus = useCallback((event: CrawlerEvent & { type: 'run:status' }) => {
    if (event.run_id !== id) return

    // Update run status from SSE event
    setRun((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        status: event.status as CrawlRun['status'],
        error: event.error ?? prev.error,
        finished_at: event.status === 'completed' || event.status === 'failed' || event.status === 'stopped'
          ? event.timestamp
          : prev.finished_at,
      }
    })
  }, [id])

  const handleTaskStatus = useCallback((event: CrawlerEvent & { type: 'task:status' }) => {
    if (event.run_id !== id) return

    // Update or add task in the list
    setTasks((prev) => {
      const existingIndex = prev.findIndex((t) => t.code === event.code)
      if (existingIndex >= 0) {
        // Update existing task
        const updated = [...prev]
        updated[existingIndex] = {
          ...updated[existingIndex],
          status: event.status as CrawlRunDetailTask['status'],
          error: event.error ?? updated[existingIndex].error,
        }
        return updated
      } else {
        // Add new task if not exists
        const newTask: CrawlRunDetailTask = {
          id: `temp-${event.code}-${Date.now()}`,
          run_id: event.run_id,
          task_name: '',
          code: event.code ?? null,
          source_url: event.source_url,
          source_name: '',
          status: event.status as CrawlRunDetailTask['status'],
          error: event.error ?? null,
          item_data: null,
          created_at: event.timestamp,
          crawled_at: null,
          saved_at: null,
        }
        return [...prev, newTask]
      }
    })
  }, [id])

  const handleEvent = useCallback((event: CrawlerEvent) => {
    // Handle run:log events to append logs
    if (event.type === 'run:log' && event.run_id === id) {
      const logEntry: RunLogEntry = {
        timestamp: event.timestamp,
        level: event.level,
        message: event.message,
        context: event.context,
      }
      setRun((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          logs: [...(prev.logs ?? []), logEntry],
        }
      })
    }
  }, [id])

  // Connect to SSE stream for real-time updates
  useCrawlerSSE({
    enabled: !!id,
    onEvent: handleEvent,
    onRunStatus: handleRunStatus,
    onTaskStatus: handleTaskStatus,
  })

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

      {run && (
        <Card title="运行日志" style={{ marginTop: 16 }}>
          <RunLogsTimeline
            logs={run.logs ?? []}
            isActive={run.status === 'queued' || run.status === 'running'}
          />
        </Card>
      )}
    </div>
  )
}

export default RunDetailPage
