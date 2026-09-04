import { useEffect } from 'react'
import { Button, Checkbox, Drawer, Form, Input, Segmented, Select, Switch, TimePicker } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import type {
  CrawlerSchedule,
  CrawlerSchedulePayload,
  ScheduleType,
  StorageMode,
} from '@/api/crawler/crawlerSchedule/types'
import styles from '../SchedulePages.module.less'

export interface CrawlerScheduleFormValues {
  name: string
  enabled: boolean
  task_ids: string[]
  schedule_type: ScheduleType
  time_of_day: Dayjs
  weekdays: number[]
  auto_storage_enabled: boolean
  storage_mode: StorageMode
  selected_storage_location?: string
}

interface ScheduleFormDrawerProps {
  open: boolean
  taskOptions: Array<{ id: string; name: string }>
  taskOptionsLoading?: boolean
  editing?: CrawlerSchedule | null
  submitting: boolean
  onCancel: () => void
  onSubmit: (payload: CrawlerSchedulePayload) => void | Promise<void>
}

const WEEKDAY_OPTIONS = [
  { label: '周一', value: 0 },
  { label: '周二', value: 1 },
  { label: '周三', value: 2 },
  { label: '周四', value: 3 },
  { label: '周五', value: 4 },
  { label: '周六', value: 5 },
  { label: '周日', value: 6 },
]

export default function ScheduleFormDrawer({
  open,
  taskOptions,
  taskOptionsLoading = false,
  editing = null,
  submitting,
  onCancel,
  onSubmit,
}: ScheduleFormDrawerProps) {
  const [form] = Form.useForm<CrawlerScheduleFormValues>()
  const scheduleType = Form.useWatch('schedule_type', form)
  const autoStorageEnabled = Form.useWatch('auto_storage_enabled', form)
  const storageMode = Form.useWatch('storage_mode', form)

  useEffect(() => {
    if (!open) return
    form.resetFields()
    if (editing) {
      form.setFieldsValue({
        name: editing.name,
        enabled: editing.enabled,
        task_ids: editing.tasks.map((task) => task.id),
        schedule_type: editing.schedule_type,
        time_of_day: dayjs(editing.time_of_day, 'HH:mm'),
        weekdays: editing.weekdays,
        auto_storage_enabled: editing.auto_storage_enabled,
        storage_mode: editing.storage_mode,
        selected_storage_location: editing.selected_storage_location ?? undefined,
      })
    }
  }, [editing, form, open])

  const handleSave = async () => {
    let values: CrawlerScheduleFormValues
    try {
      values = await form.validateFields()
    } catch {
      // Field errors are rendered inline by antd Form.
      return
    }
    const payload: CrawlerSchedulePayload = {
      name: values.name.trim(),
      enabled: values.enabled ?? true,
      task_ids: values.task_ids,
      schedule_type: values.schedule_type,
      time_of_day: values.time_of_day.format('HH:mm'),
      weekdays: values.schedule_type === 'weekly' ? values.weekdays : [],
      auto_storage_enabled: values.auto_storage_enabled ?? false,
      storage_mode: values.storage_mode ?? 'single',
      selected_storage_location: values.selected_storage_location?.trim() || null,
    }
    try {
      await onSubmit(payload)
    } catch {
      // The parent owns user-facing error reporting.
    }
  }

  return (
    <Drawer
      title={editing ? '编辑定时任务' : '新建定时任务'}
      placement="right"
      size={540}
      open={open}
      onClose={onCancel}
      className={styles.scheduleFormDrawer}
      footer={
        <div className={styles.drawerFooter}>
          <Button disabled={submitting} onClick={onCancel}>
            取消
          </Button>
          <Button type="primary" autoInsertSpace={false} loading={submitting} onClick={() => void handleSave()}>
            保存
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        disabled={submitting}
        initialValues={{
          name: '',
          enabled: true,
          task_ids: [],
          schedule_type: 'daily' as ScheduleType,
          weekdays: [],
          auto_storage_enabled: false,
          storage_mode: 'single' as StorageMode,
        }}
      >
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
          <Input maxLength={200} placeholder="给定时任务起个名字" />
        </Form.Item>

        <Form.Item name="task_ids" label="任务" rules={[{ required: true, message: '请选择任务' }]}>
          <Select
            mode="multiple"
            loading={taskOptionsLoading}
            options={taskOptions.map((task) => ({ value: task.id, label: task.name }))}
            placeholder="选择要定时执行的任务"
          />
        </Form.Item>

        <Form.Item name="schedule_type" label="执行频率">
          <Segmented
            block
            options={[
              { label: '每天', value: 'daily' },
              { label: '每周', value: 'weekly' },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="time_of_day"
          label="执行时间"
          rules={[{ required: true, message: '请选择时间' }]}
        >
          <TimePicker format="HH:mm" placeholder="选择时间" style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="weekdays"
          label="每周执行日"
          dependencies={['schedule_type']}
          rules={[
            {
              validator: (_, value: number[] | undefined) => {
                if (form.getFieldValue('schedule_type') === 'weekly' && (!value || value.length === 0)) {
                  return Promise.reject(new Error('请选择至少一天'))
                }
                return Promise.resolve()
              },
            },
          ]}
        >
          <Checkbox.Group disabled={scheduleType !== 'weekly'} options={WEEKDAY_OPTIONS} />
        </Form.Item>

        <Form.Item name="enabled" label="启用" valuePropName="checked" tooltip="停用后不会按计划执行">
          <Switch />
        </Form.Item>

        <Form.Item name="auto_storage_enabled" label="执行后自动存储" valuePropName="checked">
          <Switch />
        </Form.Item>

        {autoStorageEnabled ? (
          <>
            <Form.Item name="storage_mode" label="存储方式">
              <Segmented
                block
                options={[
                  { label: '单盘', value: 'single' },
                  { label: '多盘', value: 'multiple' },
                ]}
              />
            </Form.Item>
            {storageMode === 'single' ? (
              <Form.Item name="selected_storage_location" label="存储位置">
                <Input maxLength={500} placeholder="留空使用任务的默认存储位置" />
              </Form.Item>
            ) : null}
          </>
        ) : null}
      </Form>
    </Drawer>
  )
}
