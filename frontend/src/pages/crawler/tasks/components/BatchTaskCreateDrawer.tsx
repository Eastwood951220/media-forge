import { useEffect } from 'react'
import { Button, Drawer, Form, Input, Select, Space, Switch } from 'antd'
import type { TaskTag } from '@/api/crawler/crawlTask/types'
import { SORT_OPTIONS } from '../taskUrlUtils'
import TaskTagSelect from './TaskTagSelect'
import styles from '../TaskPages.module.less'

export interface BatchTaskCreateFormValues {
  urls: string[]
  has_magnet: boolean
  has_chinese_sub: boolean
  sort_type: number
  is_skip: boolean
  tag_names: string[]
}

interface BatchTaskCreateDrawerProps {
  open: boolean
  submitting: boolean
  failedUrls: string[]
  tagOptions?: TaskTag[]
  tagOptionsLoading?: boolean
  onCancel: () => void
  onSubmit: (values: BatchTaskCreateFormValues) => void | Promise<void>
}

function parseUrlLines(value: string | undefined): string[] {
  return (value ?? '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function BatchTaskCreateDrawer({
  open,
  submitting,
  failedUrls,
  tagOptions = [],
  tagOptionsLoading = false,
  onCancel,
  onSubmit,
}: BatchTaskCreateDrawerProps) {
  const [form] = Form.useForm<{
    urlText: string
    has_magnet: boolean
    has_chinese_sub: boolean
    sort_type: number
    is_skip: boolean
    tag_names: string[]
  }>()

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      urlText: failedUrls.length > 0 ? failedUrls.join('\n') : form.getFieldValue('urlText') ?? '',
      has_magnet: form.getFieldValue('has_magnet') ?? true,
      has_chinese_sub: form.getFieldValue('has_chinese_sub') ?? false,
      sort_type: form.getFieldValue('sort_type') ?? 0,
      is_skip: form.getFieldValue('is_skip') ?? false,
      tag_names: form.getFieldValue('tag_names') ?? [],
    })
  }, [failedUrls, form, open])

  const handleSave = async () => {
    const values = await form.validateFields()
    const urls = parseUrlLines(values.urlText)
    if (urls.length === 0) {
      form.setFields([{ name: 'urlText', errors: ['请至少输入 1 个 URL'] }])
      return
    }
    await onSubmit({
      urls,
      has_magnet: values.has_magnet ?? true,
      has_chinese_sub: values.has_chinese_sub ?? false,
      sort_type: values.sort_type ?? 0,
      is_skip: values.is_skip ?? false,
      tag_names: values.tag_names ?? [],
    })
  }

  return (
    <Drawer
      title="批量新建任务"
      placement="right"
      open={open}
      onClose={onCancel}
      width={560}
      className={styles.batchTaskDrawer}
      footer={
        <div className={styles.urlEntryDrawerFooter}>
          <Button onClick={onCancel} disabled={submitting}>取消</Button>
          <Button type="primary" onClick={() => void handleSave()} loading={submitting}>保存</Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        disabled={submitting}
        initialValues={{
          urlText: '',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          is_skip: false,
          tag_names: [],
        }}
      >
        <Form.Item name="urlText" label="URL 列表" required>
          <Input.TextArea rows={12} placeholder="每行一个 URL" />
        </Form.Item>
        <Space size={16} wrap>
          <Form.Item name="has_magnet" label="磁力" valuePropName="checked">
            <Switch checkedChildren="有" unCheckedChildren="不限" />
          </Form.Item>
          <Form.Item name="has_chinese_sub" label="中文字幕" valuePropName="checked">
            <Switch checkedChildren="有" unCheckedChildren="不限" />
          </Form.Item>
          <Form.Item name="is_skip" label="创建后禁用" valuePropName="checked">
            <Switch checkedChildren="是" unCheckedChildren="否" />
          </Form.Item>
        </Space>
        <Form.Item name="sort_type" label="排序方式">
          <Select options={SORT_OPTIONS} />
        </Form.Item>
        <Form.Item name="tag_names" label="任务标签">
          <TaskTagSelect options={tagOptions} loading={tagOptionsLoading} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
