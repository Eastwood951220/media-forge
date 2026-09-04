import { useCallback, useState } from 'react'
import { App } from 'antd'
import { createTaskUrlRun } from '@/api/crawler/crawlTask'
import type { CrawlTask, TaskUrlRunFormValues } from '@/api/crawler/crawlTask/types'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'

interface UseTaskUrlRunOptions {
  onSubmitted: () => void | Promise<void>
}

export function useTaskUrlRun({ onSubmitted }: UseTaskUrlRunOptions) {
  const { message } = App.useApp()
  const [selectedTask, setSelectedTask] = useState<CrawlTask | null>(null)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const openTaskUrlRun = useCallback((task: CrawlTask) => {
    setSelectedTask(task)
    setOpen(true)
  }, [])

  const closeTaskUrlRun = useCallback(() => {
    if (submitting) return
    setOpen(false)
    setSelectedTask(null)
  }, [submitting])

  const submitTaskUrlRun = useCallback(async (values: TaskUrlRunFormValues) => {
    if (!selectedTask) return
    setSubmitting(true)
    try {
      const result = await createTaskUrlRun(selectedTask.id, values)
      useCrawlerRuntimeStore.getState().upsertTaskRuntime({
        task_id: selectedTask.id,
        runtime_status: 'queued',
        latest_run_id: result.run_id ?? null,
        state_updated_at: new Date().toISOString(),
        last_run_at: new Date().toISOString(),
      })
      message.success('URL 爬取任务已提交')
      setOpen(false)
      setSelectedTask(null)
      await onSubmitted()
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'URL 爬取任务提交失败')
    } finally {
      setSubmitting(false)
    }
  }, [message, onSubmitted, selectedTask])

  return {
    selectedTask,
    open,
    submitting,
    openTaskUrlRun,
    closeTaskUrlRun,
    submitTaskUrlRun,
  }
}
