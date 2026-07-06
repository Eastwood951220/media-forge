import { useCallback, useEffect, useState } from 'react'
import { message } from 'antd'
import { getCrawlerRun, getCrawlerRunLogs, getCrawlerRunTasks, restartCrawlerRun, stopCrawlerRun } from '@/api/crawlerRun'
import type { CrawlRun, CrawlRunDetailTask, RunLogEntry } from '@/api/crawlerRun/types'

export function useRunDetail(id: string | undefined) {
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

  return {
    actionLoading,
    fetchLogs,
    fetchRun,
    fetchTasks,
    handleRestart,
    handleStop,
    keyword,
    loading,
    logs,
    pageSize,
    resyncSnapshot,
    run,
    setKeyword,
    setLogs,
    setPageSize,
    setRun,
    setStatusFilter,
    setTasks,
    statusFilter,
    tasks,
  }
}
