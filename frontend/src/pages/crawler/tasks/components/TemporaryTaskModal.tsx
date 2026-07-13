import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input, Modal, Select, Space, Typography } from 'antd'
import type { TemporaryCrawlRunCreateParams, TaskDictItem } from '@/api/crawlTask/types'

interface TemporaryTaskModalProps {
  open: boolean
  tasks: TaskDictItem[]
  tasksLoading: boolean
  tasksError: string | null
  submitting: boolean
  onCancel: () => void
  onReloadTasks: () => Promise<void> | void
  onSubmit: (payload: TemporaryCrawlRunCreateParams) => Promise<void>
}

interface FormValues {
  task_id: string
  detail_urls: Array<{ url: string }>
}

function normalizeAndValidateUrls(rows: Array<{ url?: string }>): string[] {
  const urls: string[] = []
  const seen = new Set<string>()
  if (rows.length === 0) {
    throw new Error('至少需要 1 条详情页 URL')
  }
  if (rows.length > 50) {
    throw new Error('临时任务最多支持 50 条详情页 URL')
  }
  rows.forEach((row, index) => {
    const url = String(row.url ?? '').trim()
    const rowNumber = index + 1
    if (!url) throw new Error(`第 ${rowNumber} 条详情页 URL 不能为空`)
    if (!/^https?:\/\/(www\.)?javdb\.com\/v\/[^/\s?#]+/i.test(url)) {
      throw new Error(`第 ${rowNumber} 条不是有效的 JavDB 详情页 URL`)
    }
    if (seen.has(url)) throw new Error(`第 ${rowNumber} 条详情页 URL 重复`)
    seen.add(url)
    urls.push(url)
  })
  return urls
}

export default function TemporaryTaskModal({
  open,
  tasks,
  tasksLoading,
  tasksError,
  submitting,
  onCancel,
  onReloadTasks,
  onSubmit,
}: TemporaryTaskModalProps) {
  const [form] = Form.useForm<FormValues>()
  const submitDisabled = Boolean(tasksError) || tasks.length === 0

  const handleFinish = async (values: FormValues) => {
    try {
      const detailUrls = normalizeAndValidateUrls(values.detail_urls ?? [])
      await onSubmit({ task_id: values.task_id, detail_urls: detailUrls })
      form.resetFields()
    } catch (error) {
      form.setFields([{ name: ['detail_urls'], errors: [error instanceof Error ? error.message : '临时任务参数错误'] }])
    }
  }

  return (
    <Modal
      title="创建临时任务"
      open={open}
      onCancel={onCancel}
      footer={null}
      width={720}
      destroyOnHidden
    >
      {tasksError && (
        <Alert
          type="error"
          showIcon
          message={tasksError}
          action={(
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void onReloadTasks()}>
              重新加载任务
            </Button>
          )}
          style={{ marginBottom: 16 }}
        />
      )}
      {!tasksError && tasks.length === 0 && (
        <Alert type="warning" showIcon message="请先创建爬虫任务" style={{ marginBottom: 16 }} />
      )}
      <Form<FormValues>
        form={form}
        layout="vertical"
        initialValues={{ detail_urls: [{ url: '' }] }}
        onFinish={(values) => void handleFinish(values)}
      >
        <Form.Item name="task_id" label="归属任务" rules={[{ required: true, message: '请选择归属任务' }]}>
          <Select
            aria-label="归属任务"
            loading={tasksLoading}
            disabled={tasksLoading || Boolean(tasksError)}
            placeholder="请选择归属任务"
            options={tasks.map((task) => ({ value: task.id, label: task.name }))}
          />
        </Form.Item>

        <Typography.Text strong>详情页 URL</Typography.Text>
        <Form.ErrorList errors={form.getFieldError('detail_urls')} />
        <Form.List name="detail_urls">
          {(fields, { add, remove }) => (
            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
              {fields.map((field) => (
                <Space key={field.key} align="baseline" style={{ display: 'flex' }}>
                  <Form.Item
                    {...field}
                    name={[field.name, 'url']}
                    rules={[{ required: true, message: '请输入 JavDB 详情页 URL' }]}
                    style={{ flex: 1, marginBottom: 8 }}
                  >
                    <Input placeholder="请输入 JavDB 详情页 URL，例如 https://javdb.com/v/..." />
                  </Form.Item>
                  {fields.length > 1 && (
                    <Button aria-label="删除详情页" icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                  )}
                </Space>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ url: '' })}>
                新增详情页
              </Button>
            </Space>
          )}
        </Form.List>

        <Space style={{ marginTop: 20 }}>
          <Button type="primary" htmlType="submit" loading={submitting} disabled={submitDisabled}>
            创建临时任务
          </Button>
          <Button onClick={onCancel}>取消</Button>
        </Space>
      </Form>
    </Modal>
  )
}
