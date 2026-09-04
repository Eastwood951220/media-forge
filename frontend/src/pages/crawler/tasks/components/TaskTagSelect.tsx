import { Select } from 'antd'
import type { TaskTag } from '@/api/crawler/crawlTask/types'

interface TaskTagSelectProps {
  value?: string[]
  onChange?: (values: string[]) => void
  options: TaskTag[]
  loading?: boolean
  placeholder?: string
  disabled?: boolean
  id?: string
}

export default function TaskTagSelect({
  value,
  onChange,
  options,
  loading = false,
  placeholder = '选择或输入标签',
  disabled = false,
  id,
}: TaskTagSelectProps) {
  return (
    <Select
      id={id}
      mode="tags"
      allowClear
      disabled={disabled}
      loading={loading}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      options={options.map((tag) => ({ value: tag.name, label: tag.name }))}
    />
  )
}
