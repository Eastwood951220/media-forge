import { useState } from 'react'
import { Button, Input, Space } from 'antd'
import { FolderOpenOutlined } from '@ant-design/icons'
import DirectoryPickerModal from './DirectoryPickerModal'

interface DirectoryPathInputProps {
  id?: string
  value?: string
  placeholder?: string
  onChange?: (value: string) => void
}

export default function DirectoryPathInput({
  id,
  value,
  placeholder,
  onChange,
}: DirectoryPathInputProps) {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          id={id}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange?.(event.target.value)}
        />
        <Button
          icon={<FolderOpenOutlined />}
          aria-label="选择文件夹"
          onClick={() => setOpen(true)}
        >
          选择文件夹
        </Button>
      </Space.Compact>
      <DirectoryPickerModal
        open={open}
        initialPath={value}
        onCancel={() => setOpen(false)}
        onSelect={(path) => {
          onChange?.(path)
          setOpen(false)
        }}
      />
    </>
  )
}
