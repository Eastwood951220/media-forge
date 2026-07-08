import { useCallback, useEffect, useState } from 'react'
import { message } from 'antd'
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks, restartCrawlerRun, retryCrawlerRunTasks, stopCrawlerRun } from '@/api/crawlerRun'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry, RunTaskSummary } from '@/api/crawlerRun/types'

const emptyTaskSummary: RunTaskSummary = {
  total: 0,
  pending_crawl: 0,
  crawling: 0,
  saved: 0,
  skipped: 0,
  crawl_failed: 0,
  save_failed: 0,
  completed: 0,
  waiting: 0,
  failed: 0,
}

export function useRunDetail(id: string | undefined) {
  const [run, setRun] = useState<CrawlRun | null>(null)
  const [logs, setLogs] = useState<RunLogEntry[]>([])
  const [tasks, setTasks] = useState<CrawlRunDetailTask[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [pageSize, setPageSize] = useState(50)
  const [taskPage, setTaskPage] = useState(1)
  const [taskTotal, setTaskTotal] = useState(0)
  const [taskSummary, setTaskSummary] = useState<RunTaskSummary>(emptyTaskSummary)
  const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | 'retry' | null>(null)

  // Reset state when run ID changes
  useEffect(() => {
    setRun(null)
    setLogs([])
    setTasks([])
    setStatusFilter(undefined)
    setKeyword('')
    setTaskPage(1)
    setTaskTotal(0)
    setTaskSummary(emptyTaskSummary)
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
        page: taskPage,
        size: pageSize,
        status: statusFilter,
        keyword: keyword || undefined,
      })
      setTasks(data.rows)
      setTaskTotal(data.total)
      setTaskSummary(data.summary)
    } finally {
      setLoading(false)
    }
  }, [id, keyword, pageSize, statusFilter, taskPage])

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

  const runRetryRequest = useCallback(
    async (payload: { detail_ids?: string[]; retry_all?: boolean }, successText: string) => {
      if (!id) return
      setActionLoading('retry')
      try {
        const retriedRun = await retryCrawlerRunTasks(id, payload)
        setRun(retriedRun)
        message.success(successText)
        resyncSnapshot()
      } catch (error) {
        const msg = error instanceof Error ? error.message : '重新爬取失败'
        message.error(msg)
        resyncSnapshot()
      } finally {
        setActionLoading(null)
      }
    },
    [id, resyncSnapshot],
  )

  const handleRetryTask = useCallback(
    async (detailId: string) => {
      await runRetryRequest({ detail_ids: [detailId], retry_all: false }, '已重新爬取该失败子任务')
    },
    [runRetryRequest],
  )

  const handleRetrySelectedTasks = useCallback(
    async (detailIds: string[]) => {
      await runRetryRequest({ detail_ids: detailIds, retry_all: false }, '已重新爬取选中失败子任务')
    },
    [runRetryRequest],
  )

  const handleRetryAllFailedTasks = useCallback(async () => {
    await runRetryRequest({ retry_all: true }, '已重新爬取全部失败子任务')
  }, [runRetryRequest])

  const handleStatusChange = useCallback((value: string | undefined) => {
    setStatusFilter(value)
    setTaskPage(1)
  }, [])

  const handleKeywordSearch = useCallback((value: string) => {
    setKeyword(value)
    setTaskPage(1)
  }, [])

  const handleTaskPageChange = useCallback((page: number, size: number) => {
    setTaskPage(page)
    setPageSize(size)
  }, [])

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

  return {
    actionLoading,
    fetchLogs,
    fetchRun,
    fetchTasks,
    handleKeywordSearch,
    handleRestart,
    handleRetryAllFailedTasks,
    handleRetrySelectedTasks,
    handleRetryTask,
    handleStatusChange,
    handleStop,
    handleTaskPageChange,
    keyword,
    loading,
    logs,
    pageSize,
    resyncSnapshot,
    run,
    setLogs,
    setRun,
    setTasks,
    statusFilter,
    taskPage,
    taskTotal,
    taskSummary,
    tasks,
  }
}
