import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { Button, Form, Input, InputNumber, Select, message } from 'antd'
import {
  createCrawlTask,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTaskCreateParams } from '@/api/crawlTask/types'
import styles from './TaskPages.module.less'

const SCHEDULE_OPTIONS = [
  { value: 'once', label: '单次执行' },
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
]

function TaskFormPage() {
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const title = useMemo(() => (isEdit ? '编辑爬取任务' : '新建爬取任务'), [isEdit])

  useEffect(() => {
    if (!taskId) return

    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          description: task.description ?? undefined,
          keywords: task.keywords,
          target_websites: task.target_websites,
          schedule: task.schedule ?? undefined,
          max_pages: task.max_pages,
          crawl_depth: task.crawl_depth,
        })
      })
      .catch(() => {
        message.error('任务详情加载失败')
      })
      .finally(() => setLoading(false))
  }, [form, taskId])

  const handleSubmit = async (values: CrawlTaskCreateParams) => {
    setSubmitting(true)
    try {
      const payload: CrawlTaskCreateParams = {
        name: values.name,
        description: values.description,
        keywords: values.keywords,
        target_websites: values.target_websites,
        schedule: values.schedule,
        max_pages: values.max_pages ?? 100,
        crawl_depth: values.crawl_depth ?? 3,
      }

      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('更新成功')
      } else {
        await createCrawlTask(payload)
        message.success('创建成功')
      }
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>使用独立页面配置任务名称、关键词、目标网站和执行限制。</p>
        </div>
      </div>

      <section className={`${styles.panel} ${styles.formPanel}`}>
        <Form<CrawlTaskCreateParams>
          form={form}
          layout="vertical"
          disabled={loading}
          initialValues={{ max_pages: 100, crawl_depth: 3 }}
          onFinish={(values) => { void handleSubmit(values) }}
        >
          <Form.Item
            name="name"
            label="任务名称"
            rules={[
              { required: true, message: '请输入任务名称' },
              { max: 200, message: '名称最多 200 个字符' },
            ]}
          >
            <Input placeholder="输入任务名称" />
          </Form.Item>

          <Form.Item name="description" label="任务描述">
            <Input.TextArea rows={3} placeholder="描述任务目的" />
          </Form.Item>

          <Form.Item
            name="keywords"
            label="关键词"
            rules={[{ required: true, message: '请至少输入一个关键词' }]}
          >
            <Select mode="tags" placeholder="输入关键词后按回车" />
          </Form.Item>

          <Form.Item
            name="target_websites"
            label="目标网站"
            rules={[{ required: true, message: '请至少输入一个目标网站' }]}
          >
            <Select mode="tags" placeholder="输入网站 URL 后按回车" />
          </Form.Item>

          <Form.Item name="schedule" label="执行计划">
            <Select allowClear placeholder="选择执行频率" options={SCHEDULE_OPTIONS} />
          </Form.Item>

          <Form.Item name="max_pages" label="最大页数">
            <InputNumber min={1} max={10000} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item name="crawl_depth" label="爬取深度">
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>

          <div className={styles.actions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新任务' : '创建任务'}
            </Button>
            <Button onClick={() => navigate({ to: '/crawler/tasks' })}>
              取消
            </Button>
          </div>
        </Form>
      </section>
    </div>
  )
}

export default TaskFormPage
