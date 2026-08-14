import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Popconfirm, Space, Table, Tag, message, Card } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteCrawlerRun, getCrawlerRuns, restartCrawlerRun, stopCrawlerRun } from '@/api/crawler/crawlerRun'
import type { CrawlRun } from '@/api/crawler/crawlerRun/types'
import { queryKeys } from '@/api/queryKeys'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { subscribeRealtime } from '@/realtime/eventSourceClient'
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import type { CrawlRunStatus } from '@/api/crawler/crawlerRun/types'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

const PAGE_SIZE_OPTIONS = ['10', '20', '50']

function RunListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])
  const listQuery = useQuery({
    queryKey: queryKeys.crawlerRuns.list(listParams),
    queryFn: () => getCrawlerRuns(listParams),
    placeholderData: (previousData) => previousData,
  })

  const runRuntimeById = useCrawlerRuntimeStore((state) => state.runRuntimeById)
  const hydrateRunRuntime = useCrawlerRuntimeStore((state) => state.hydrateRunRuntime)
  const upsertRunRuntime = useCrawlerRuntimeStore((state) => state.upsertRunRuntime)
  const removeRunRuntime = useCrawlerRuntimeStore((state) => state.removeRunRuntime)
  const connectionStatus = useCrawlerRuntimeStore((state) => state.connectionStatus)
  const markResyncRequired = useCrawlerRuntimeStore((state) => state.markResyncRequired)

  // Hydrate baseline run runtimes from REST data (only for rows not yet in store)
  useEffect(() => {
    const rows = listQuery.data?.rows ?? []
    if (rows.length === 0) return
    const entries: Array<[string, import('@/realtime/types').CrawlRunRuntime]> = []
    for (const run of rows) {
      if (!runRuntimeById[run.id]) {
        entries.push([
          run.id,
          {
            run_id: run.id,
            status: run.status,
            error: null,
            started_at: null,
            finished_at: null,
            state_updated_at: run.created_at,
          },
        ])
      }
    }
    if (entries.length > 0) {
      hydrateRunRuntime(Object.fromEntries(entries))
    }
  }, [listQuery.data?.rows, hydrateRunRuntime, runRuntimeById])

  // Overlay store status onto REST rows
  const runs = useMemo(
    () =>
      (listQuery.data?.rows ?? []).map((run) => ({
        ...run,
        status: (runRuntimeById[run.id]?.status ?? run.status) as CrawlRunStatus,
        error: runRuntimeById[run.id]?.error ?? run.error,
      })),
    [listQuery.data?.rows, runRuntimeById],
  )

  const total = listQuery.data?.total ?? 0
  const loading = listQuery.isFetching
  const realtimeReady = connectionStatus === 'connected'

  const refreshRuns = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRuns.list(listParams) })
  }, [listParams, queryClient])

  // Realtime subscription for individual run status updates
  // Coalescing refresh: if a run_id is unknown in the current REST rows, schedule
  // a single debounced list refresh instead of refetching on every event.
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    const unsubscribe = subscribeRealtime<import('@/realtime/types').CrawlerRunStatusUpdatedPayload>(
      'crawler.run.status.updated',
      (event) => {
        const runId = event.payload.run_id
        // Only schedule refresh for unknown run IDs
        if (!runRuntimeById[runId] && !listQuery.data?.rows.find((r) => r.id === runId)) {
          if (!refreshTimerRef.current) {
            refreshTimerRef.current = setTimeout(() => {
              refreshTimerRef.current = null
              refreshRuns()
            }, 500)
          }
        }
        upsertRunRuntime(event.payload)
      },
    )
    return () => {
      unsubscribe()
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
    }
  }, [upsertRunRuntime, runRuntimeById, listQuery.data?.rows, refreshRuns])

  // Realtime subscription for resync — refresh the list once so cleared store is rehydrated
  useEffect(() => {
    const unsubscribe = subscribeRealtime('system.resync_required', () => {
      markResyncRequired('run-list')
      refreshRuns()
    })
    return unsubscribe
  }, [markResyncRequired, refreshRuns])

  useRouteActivationRefresh(refreshRuns)

  const handleStop = useCallback(async (run: CrawlRun) => {
    try {
      await stopCrawlerRun(run.id)
      message.success('已停止运行')
    } catch {
      message.error('停止失败')
    }
  }, [])

  const handleRestart = useCallback(async (run: CrawlRun) => {
    try {
      await restartCrawlerRun(run.id)
      message.success('已重启运行')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '重启失败'
      message.error(msg)
    }
  }, [])

  const handleDelete = useCallback(async (run: CrawlRun) => {
    try {
      await deleteCrawlerRun(run.id)
      message.success('已删除运行记录')
      // Remove from store so it disappears immediately
      removeRunRuntime(run.id)
      const nextPage = runs.length === 1 && current > 1 ? current - 1 : current
      if (nextPage !== current) {
        setCurrent(nextPage)
        return
      }
      refreshRuns()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除失败'
      message.error(msg)
    }
  }, [current, refreshRuns, removeRunRuntime, runs.length])

  const columns: ColumnsType<CrawlRun> = [
    {
      title: '任务名称',
      dataIndex: 'task_name',
      key: 'task_name',
      render: (name: string) => (
        <span style={{ fontWeight: 500 }}>{name}</span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const { text, color } = statusLabels[status] || { text: status, color: 'default' }
        return (
          <Tag
            color={color}
            style={{
              animation: status === 'running' ? 'statusPulse 2s ease-in-out infinite' : undefined,
            }}
          >
            {text}
          </Tag>
        )
      },
    },
    {
      title: '模式',
      dataIndex: 'crawl_mode',
      key: 'crawl_mode',
      width: 100,
      render: (mode: string) => {
        const modeLabels: Record<string, { text: string; color: string }> = {
          incremental: { text: '增量', color: 'blue' },
          full: { text: '全量', color: 'purple' },
          temporary: { text: '临时', color: 'orange' },
        }
        const { text, color } = modeLabels[mode] || { text: mode, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => (
        <span style={{ color: 'var(--text-secondary, #6b7280)', fontSize: 13 }}>
          {new Date(time).toLocaleString()}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Button
            size="small"
            type="primary"
            ghost
            icon={<EyeOutlined />}
            onClick={() => void navigate({ to: `/crawler/runs/${record.id}` })}
          >
            详情
          </Button>
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
          {record.status !== 'queued' && record.status !== 'running' && (
            <Popconfirm
              title="删除运行记录"
              description="仅删除运行记录和子任务记录，不会删除影片数据。"
              okText="确定"
              cancelText="取消"
              onConfirm={() => handleDelete(record)}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      style={{
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
      }}
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={runs}
        loading={loading}
        pagination={{
          current,
          total,
          pageSize,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showSizeChanger: true,
          showTotal: (count) => (realtimeReady ? `共 ${count} 条` : '同步中'),
          onChange: (page, size) => {
            setCurrent(page)
            setPageSize(size)
          },
        }}
      />
    </Card>
  )
}

export default RunListPage