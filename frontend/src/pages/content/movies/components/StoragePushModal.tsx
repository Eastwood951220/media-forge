import { useEffect, useMemo, useState } from 'react'
import { Form, Input, Modal, Segmented, Select } from 'antd'
import type { StorageMode } from '@/api/storage/storageTasks/types'

type TargetMode = 'default' | 'existing' | 'custom'

type PushMovie = {
  _id: string
  code?: string
  source_name?: string
  storage_locations?: string[]
}

type Props = {
  open: boolean
  mode: 'single' | 'batch'
  movies: PushMovie[]
  selectedRowKeys: React.Key[]
  loading: boolean
  defaultAlias?: string
  onCancel: () => void
  onSubmit: (values: { alias?: string; storageMode: StorageMode; selectedStorageLocation?: string }) => void
}

function StoragePushModal({ open, mode, movies, selectedRowKeys, loading, defaultAlias, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<{ alias?: string; existingStorageLocation?: string; customStorageLocation?: string }>()
  const [storageMode, setStorageMode] = useState<StorageMode>('single')
  const [targetMode, setTargetMode] = useState<TargetMode>('default')
  const firstMovie = movies[0]
  const locationOptions = useMemo(() => {
    const values = movies.flatMap((movie) => movie.storage_locations ?? [])
    return Array.from(new Set(values)).map((value) => ({ value, label: value }))
  }, [movies])

  useEffect(() => {
    if (open && defaultAlias) {
      form.setFieldsValue({ alias: defaultAlias })
    }
  }, [open, defaultAlias, form])

  return (
    <Modal
      title={mode === 'single' ? '推送存储' : '批量推送存储'}
      open={open}
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => onSubmit({
        alias: form.getFieldValue('alias'),
        storageMode,
        selectedStorageLocation: targetMode === 'existing'
          ? form.getFieldValue('existingStorageLocation')
          : targetMode === 'custom'
            ? form.getFieldValue('customStorageLocation')?.trim() || undefined
            : undefined,
      })}
    >
      <Form form={form} layout="vertical" initialValues={{ existingStorageLocation: locationOptions[0]?.value }}>
        <Form.Item label="别名" name="alias">
          <Input />
        </Form.Item>
        <Form.Item label="存储范围">
          <Select
            value={storageMode}
            onChange={(value) => {
              setStorageMode(value)
              if (value === 'multiple') setTargetMode('default')
            }}
            options={[
              { value: 'single', label: '单盘' },
              { value: 'multiple', label: '多盘' },
            ]}
          />
        </Form.Item>
        {storageMode === 'single' && (
          <Form.Item label="目标策略">
            <Segmented
              block
              value={targetMode}
              onChange={(value) => setTargetMode(value as TargetMode)}
              options={[
                { label: '默认路径', value: 'default' },
                { label: '选择已有路径', value: 'existing' },
                { label: '指定路径', value: 'custom' },
              ]}
            />
          </Form.Item>
        )}
        {storageMode === 'single' && targetMode === 'existing' && (
          <Form.Item label="已有路径" name="existingStorageLocation">
            <Select options={locationOptions} />
          </Form.Item>
        )}
        {storageMode === 'single' && targetMode === 'custom' && (
          <Form.Item label="指定路径" name="customStorageLocation">
            <Input maxLength={500} placeholder="填写 target_folder 下的相对路径" />
          </Form.Item>
        )}
        <div>{mode === 'batch' ? `已选择 ${selectedRowKeys.length} 条` : firstMovie?.code}</div>
      </Form>
    </Modal>
  )
}

export default StoragePushModal
