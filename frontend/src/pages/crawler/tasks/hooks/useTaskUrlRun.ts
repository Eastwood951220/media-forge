import { useCallback, useState } from 'react'
import { App } from 'antd'
import { createTaskUrlRun } from '@/api/crawlTask'
import type { CrawlTask, TaskUrlRunFormValues } from '@/api/crawlTask/types'

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
      await createTaskUrlRun(selectedTask.id, values)
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
