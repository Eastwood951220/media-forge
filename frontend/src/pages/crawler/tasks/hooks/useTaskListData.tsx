import { useCallback, useState } from 'react'
import { Modal, Select, Typography, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteCrawlTask,
  getCrawlTaskCount,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
import type {
  CrawlTask,
  CrawlTaskRuntimeSnapshot,
  CrawlTaskRuntimeStats,
  DeleteMode,
} from '@/api/crawlTask/types'
import { restartCrawlerRun, runCrawlTask, stopCrawlerRun } from '@/api/crawlerRun'
import type { CrawlMode } from '@/api/crawlerRun/types'
import { queryKeys } from '@/api/queryKeys'
import styles from '../TaskPages.module.less'
import { initialStats } from '../utils/runtimeStats'

const deleteModeOptions: Array<{ value: DeleteMode; label: string }> = [
  { value: 'task_only', label: '仅删除任务' },
  { value: 'task_and_movies', label: '删除任务和关联影片' },
  { value: 'task_movies_and_cloud', label: '删除任务、关联影片和云存储' },
]

export function useTaskListData() {
  const queryClient = useQueryClient()
  const [runtimeByTaskId, setRuntimeByTaskId] = useState<Record<string, CrawlTaskRuntimeSnapshot>>({})
  const [stats, setStats] = useState<CrawlTaskRuntimeStats>(initialStats)

  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const listParams = { page: current, size: pageSize }
  const countParams = {}

  const listQuery = useQuery({
    queryKey: queryKeys.crawlerTasks.list(listParams),
    queryFn: () => getCrawlTasks(listParams),
    placeholderData: (previousData) => previousData,
  })

  const countQuery = useQuery({
    queryKey: queryKeys.crawlerTasks.count(countParams),
    queryFn: () => getCrawlTaskCount(countParams),
  })

  const tasks = listQuery.data?.rows ?? []
  const total = countQuery.data?.total ?? 0
  const loading = listQuery.isLoading
  const hasMore = listQuery.data?.has_more ?? false

  // Initialize runtime stats from list response
  const fetchRuntimeStatuses = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.crawlerTasks.list(listParams) })
  }, [queryClient, listParams])

  const refreshList = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerTasks.list(listParams) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawlerTasks.count(countParams) })
  }, [queryClient, listParams, countParams])

  // Update runtime stats when list data changes
  if (listQuery.data?.runtime) {
    const runtime = listQuery.data.runtime
    const currentRuntimeByTaskId = Object.fromEntries(runtime.tasks.map((item) => [item.task_id, item]))
    if (JSON.stringify(currentRuntimeByTaskId) !== JSON.stringify(runtimeByTaskId)) {
      setRuntimeByTaskId(currentRuntimeByTaskId)
      setStats(runtime.stats)
    }
  }

  const handleDelete = useCallback(
    (task: CrawlTask) => {
      let selectedMode: DeleteMode = 'task_only'

      Modal.confirm({
        title: '确认删除',
        content: (
          <div>
            <p>确定删除任务「{task.name}」？</p>
            <div className={styles.deleteModeRow}>
              <Typography.Text className={styles.deleteModeLabel}>删除模式</Typography.Text>
              <Select<DeleteMode>
                aria-label="删除模式"
                defaultValue="task_only"
                options={deleteModeOptions}
                onChange={(value) => {
                  selectedMode = value
                }}
                style={{ width: '100%' }}
              />
            </div>
            <Typography.Text type="danger" className={styles.deleteWarning}>
              删除任务和关联影片将永久删除该任务独占的影片数据，且不可撤销。
            </Typography.Text>
          </div>
        ),
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        width: 500,
        onOk: async () => {
          const result = await deleteCrawlTask(task.id, selectedMode)
          const movieMsg =
            selectedMode !== 'task_only' ? `，已删除 ${result?.deleted_movies ?? 0} 部关联影片` : ''
          const cloudMsg =
            selectedMode === 'task_movies_and_cloud'
              ? `，已删除 ${result?.cloud_deleted_folders?.length ?? 0} 个云存储文件夹`
              : ''
          message.success(`删除成功${movieMsg}${cloudMsg}`)
          refreshList()
        },
      })
    },
    [refreshList],
  )

  const handleToggleSkip = useCallback(
    async (task: CrawlTask) => {
      await updateCrawlTask(task.id, { is_skip: !task.is_skip })
      message.success(task.is_skip ? '任务已启用' : '任务已禁用')
      refreshList()
    },
    [refreshList],
  )

  const handleRun = useCallback(
    async (task: CrawlTask, mode: CrawlMode) => {
      try {
        await runCrawlTask(task.id, mode)
        message.success(`已提交${mode === 'incremental' ? '增量' : '全量'}爬取任务`)
        void fetchRuntimeStatuses()
      } catch {
        message.error('启动爬取任务失败')
      }
    },
    [fetchRuntimeStatuses],
  )

  const handleStop = useCallback(
    async (task: CrawlTask) => {
      const runtime = runtimeByTaskId[task.id]
      if (!runtime?.latest_run_id) return
      try {
        await stopCrawlerRun(runtime.latest_run_id)
        message.success('已停止运行')
        refreshList()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '停止失败'
        message.error(msg)
        void fetchRuntimeStatuses()
      }
    },
    [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
  )

  const handleRestart = useCallback(
    async (task: CrawlTask) => {
      const runtime = runtimeByTaskId[task.id]
      if (!runtime?.latest_run_id) return
      try {
        await restartCrawlerRun(runtime.latest_run_id)
        message.success('已重启运行')
        refreshList()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '重启失败'
        message.error(msg)
        void fetchRuntimeStatuses()
      }
    },
    [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
  )

  return {
    current,
    pageSize,
    hasMore,
    total,
    countLoading: countQuery.isLoading,
    setCurrent,
    setPageSize,
    fetchRuntimeStatuses,
    handleDelete,
    handleRestart,
    handleRun,
    handleStop,
    handleToggleSkip,
    loading,
    refreshList,
    runtimeByTaskId,
    setRuntimeByTaskId,
    setStats,
    stats,
    tasks,
  }
}
