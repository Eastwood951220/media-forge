import { useMemo, useState } from 'react'
import { Form, Input, Modal, Select } from 'antd'
import type { StorageMode } from '@/api/storage/storageTasks/types'

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
  onCancel: () => void
  onSubmit: (values: { alias?: string; storageMode: StorageMode; selectedStorageLocation?: string }) => void
}

function StoragePushModal({ open, mode, movies, selectedRowKeys, loading, onCancel, onSubmit }: Props) {
  const [form] = Form.useForm<{ alias?: string; selectedStorageLocation?: string }>()
  const [storageMode, setStorageMode] = useState<StorageMode>('single')
  const firstMovie = movies[0]
  const locationOptions = useMemo(
    () => (firstMovie?.storage_locations ?? []).map((value) => ({ value, label: value })),
    [firstMovie],
  )

  return (
    <Modal
      title={mode === 'single' ? '推送存储' : '批量推送存储'}
      open={open}
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => onSubmit({
        alias: form.getFieldValue('alias'),
        storageMode,
        selectedStorageLocation: form.getFieldValue('selectedStorageLocation'),
      })}
    >
      <Form form={form} layout="vertical" initialValues={{ selectedStorageLocation: locationOptions[0]?.value }}>
        <Form.Item label="别名" name="alias">
          <Input />
        </Form.Item>
        <Form.Item label="存储模式">
          <Select
            value={storageMode}
            onChange={setStorageMode}
            options={[
              { value: 'single', label: '单个' },
              { value: 'multiple', label: '多个' },
            ]}
          />
        </Form.Item>
        {mode === 'single' && storageMode === 'single' && (
          <Form.Item label="目标文件夹" name="selectedStorageLocation">
            <Select options={locationOptions} />
          </Form.Item>
        )}
        <div>{mode === 'batch' ? `已选择 ${selectedRowKeys.length} 条` : firstMovie?.code}</div>
      </Form>
    </Modal>
  )
}

export default StoragePushModal
