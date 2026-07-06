import { App } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { useCallback, useState } from 'react'
import { createCrawlTask, updateCrawlTask } from '@/api/crawlTask'
import type { CrawlTaskCreateParams } from '@/api/crawlTask/types'

export function useTaskFormSubmit(
  taskId: string | undefined,
  isEdit: boolean,
  options: {
    onCancel: () => void
    onSuccess: () => void
  },
) {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)

  const submit = useCallback(async (payload: CrawlTaskCreateParams) => {
    setSubmitting(true)
    try {
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      options.onSuccess()
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }, [isEdit, message, navigate, options, taskId])

  const cancel = useCallback(() => {
    options.onCancel()
    void navigate({ to: '/crawler/tasks' })
  }, [navigate, options])

  return { cancel, submit, submitting }
}
