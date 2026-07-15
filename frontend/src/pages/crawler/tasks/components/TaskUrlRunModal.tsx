import { Form, Modal, Select, Space, Tag, Typography } from 'antd'
import type { CrawlTask, TaskUrlEntry, TaskUrlRunFormValues } from '@/api/crawlTask/types'

interface TaskUrlRunModalProps {
  open: boolean
  task: CrawlTask | null
  submitting: boolean
  onCancel: () => void
  onSubmit: (values: TaskUrlRunFormValues) => Promise<void>
}

function optionLabel(url: TaskUrlEntry) {
  const title = url.url_name?.trim() || url.url
  return (
    <Space direction="vertical" size={2}>
      <Typography.Text>{title}</Typography.Text>
      <Space size={4}>
        <Tag>{url.url_type}</Tag>
        {url.has_magnet ? <Tag color="blue">磁链</Tag> : null}
        {url.has_chinese_sub ? <Tag color="green">字幕</Tag> : null}
      </Space>
    </Space>
  )
}

export default function TaskUrlRunModal({
  open,
  task,
  submitting,
  onCancel,
  onSubmit,
}: TaskUrlRunModalProps) {
  const [form] = Form.useForm<TaskUrlRunFormValues>()
  const options = (task?.urls ?? [])
    .slice()
    .sort((left, right) => (left.position ?? 0) - (right.position ?? 0))
    .filter((url) => Boolean(url.id))
    .map((url) => ({
      value: String(url.id),
      label: optionLabel(url),
    }))

  const handleFinish = async (values: TaskUrlRunFormValues) => {
    await onSubmit(values)
    form.resetFields()
  }

  return (
    <Modal
      title={task ? `URL 爬取 - ${task.name}` : 'URL 爬取'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      okText="开始爬取"
      cancelText="取消"
      confirmLoading={submitting}
      destroyOnHidden
      afterOpenChange={(nextOpen) => {
        if (!nextOpen) form.resetFields()
      }}
    >
      <Form<TaskUrlRunFormValues>
        form={form}
        layout="vertical"
        initialValues={{ crawl_mode: 'incremental', url_ids: [] }}
        onFinish={(values) => void handleFinish(values)}
      >
        <Form.Item
          name="url_ids"
          label="选择 URL"
          rules={[{ required: true, message: '请选择至少 1 条任务 URL' }]}
        >
          <Select
            aria-label="选择 URL"
            mode="multiple"
            options={options}
            placeholder="请选择任务 URL"
            disabled={submitting || options.length === 0}
            optionLabelProp="value"
          />
        </Form.Item>
        <Form.Item
          name="crawl_mode"
          label="爬取模式"
          rules={[{ required: true, message: '请选择爬取模式' }]}
        >
          <Select
            aria-label="爬取模式"
            disabled={submitting}
            options={[
              { value: 'incremental', label: '增量爬取' },
              { value: 'full', label: '全量爬取' },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
