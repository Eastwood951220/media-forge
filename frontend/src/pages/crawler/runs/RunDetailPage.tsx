import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { DeleteOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Input, message, Modal, Select, Space, Table, Tag } from 'antd'
import RunLogsTimeline from './components/RunLogsTimeline'
import type { ColumnsType } from 'antd/es/table'
import { deleteCrawlerRun, getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks, restartCrawlerRun, stopCrawlerRun } from '@/api/crawlerRun'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type {
  CrawlerRunDetailUpdatedPayload,
  CrawlerRunLogAppendedPayload,
  CrawlerRunUpdatedPayload,
} from '@/realtime/types'

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
  const navigate = useNavigate()
  const [run, setRun] = useState<CrawlRun | null>(null)
  const [logs, setLogs] = useState<RunLogEntry[]>([])
  const [tasks, setTasks] = useState<CrawlRunDetailTask[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [pageSize, setPageSize] = useState(50)
  const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | null>(null)

  // Reset state when run ID changes
  useEffect(() => {
    setRun(null)
    setLogs([])
    setTasks([])
    setStatusFilter(undefined)
    setKeyword('')
  }, [id])

  // Fetch helpers
  const fetchRun = useCallback(async () => {
    if (!id) return
    const data = await getCrawlerRun(id)
    setRun(data)
  }, [id])

  const fetchLogs = useCallback(async () => {
    if (!id) return
    const data = await getCrawlerRunLogs(id)
    setLogs(data)
  }, [id])

  const fetchTasks = useCallback(async () => {
    if (!id) return
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
  }, [id, keyword, statusFilter])

  const resyncSnapshot = useCallback(() => {
    void fetchRun()
    void fetchLogs()
    void fetchTasks()
  }, [fetchLogs, fetchRun, fetchTasks])

  const handleStop = useCallback(async () => {
    if (!id) return
    setActionLoading('stop')
    try {
      const stoppedRun = await stopCrawlerRun(id)
      setRun(stoppedRun)
      message.success('已停止运行')
      resyncSnapshot()
    } catch (error) {
      const msg = error instanceof Error ? error.message : '停止失败'
      message.error(msg)
    } finally {
      setActionLoading(null)
    }
  }, [id, resyncSnapshot])

  const handleDelete = useCallback(() => {
    if (!id || !run) return
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除运行记录"${run.task_name}"吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteCrawlerRun(id)
          message.success('已删除运行记录')
          void navigate({ to: '/crawler/runs' })
        } catch {
          message.error('删除失败')
        }
      },
    })
  }, [id, run, navigate])

  const handleRestart = useCallback(async () => {
    if (!id) return
    setActionLoading('restart')
    try {
      const restartedRun = await restartCrawlerRun(id)
      setRun(restartedRun)
      message.success('已重启运行')
      resyncSnapshot()
    } catch (error) {
      const msg = error instanceof Error ? error.message : '重启失败'
      message.error(msg)
    } finally {
      setActionLoading(null)
    }
  }, [id, resyncSnapshot])

  // Initial fetch effects
  useEffect(() => {
    void fetchRun()
  }, [fetchRun])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    void fetchTasks()
  }, [fetchTasks])

  // Realtime subscription effects
  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeRun = subscribeRealtime<CrawlerRunUpdatedPayload>(
      'crawler.run.updated',
      (event) => {
        if (event.resource_id !== id) return
        setRun((currentRun) => ({
          ...event.payload,
          logs: currentRun?.logs ?? [],
        }))
        if (['completed', 'failed', 'stopped'].includes(event.payload.status)) {
          void fetchLogs()
        }
      },
    )

    const unsubscribeDetails = subscribeRealtime<CrawlerRunDetailUpdatedPayload>(
      'crawler.run.detail.updated',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
        setTasks((currentTasks) => {
          const byId = new Map(currentTasks.map((task) => [task.id, task]))
          for (const task of event.payload.tasks) {
            const matchesStatus = !statusFilter || task.status === statusFilter
            const normalizedKeyword = keyword.trim().toLowerCase()
            const matchesKeyword = !normalizedKeyword
              || (task.code ?? '').toLowerCase().includes(normalizedKeyword)
              || task.source_name.toLowerCase().includes(normalizedKeyword)
            if (matchesStatus && matchesKeyword) {
              byId.set(task.id, task)
            } else {
              byId.delete(task.id)
            }
          }
          return Array.from(byId.values()).sort((a, b) => (
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          ))
        })
      },
    )

    const unsubscribeLogs = subscribeRealtime<CrawlerRunLogAppendedPayload>(
      'crawler.run.log.appended',
      (event) => {
        if (event.resource_id !== id || event.payload.run_id !== id) return
        setLogs((currentLogs) => [...currentLogs, event.payload.log])
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        resyncSnapshot()
      },
    )

    return () => {
      unsubscribeRun()
      unsubscribeDetails()
      unsubscribeLogs()
      unsubscribeResync()
    }
  }, [id, fetchLogs, keyword, resyncSnapshot, statusFilter])

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
        <Card
          title={`运行详情 - ${run.task_name}`}
          extra={(
            <Space>
              {(run.status === 'queued' || run.status === 'running') && (
                <Button
                  danger
                  icon={<StopOutlined />}
                  loading={actionLoading === 'stop'}
                  onClick={() => void handleStop()}
                >
                  停止
                </Button>
              )}
              {(run.status === 'stopped' || run.status === 'failed') && (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  loading={actionLoading === 'restart'}
                  onClick={() => void handleRestart()}
                >
                  重启
                </Button>
              )}
              {run.status !== 'running' && (
                <Button
                  danger
                  icon={<DeleteOutlined />}
                  onClick={handleDelete}
                >
                  删除
                </Button>
              )}
            </Space>
          )}
          style={{ marginBottom: 16 }}
        >
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
          pagination={{
            pageSize,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100', '200'],
            onChange: (_page, size) => setPageSize(size),
          }}
        />
      </Card>

      {run && (
        <Card title="运行日志" style={{ marginTop: 16 }}>
          <RunLogsTimeline
            logs={logs}
            isActive={run.status === 'queued' || run.status === 'running'}
          />
        </Card>
      )}
    </div>
  )
}

export default RunDetailPage
