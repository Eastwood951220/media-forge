import { useState } from 'react'
import { Input, Tag } from 'antd'
import styles from '../StorageConfigPage.module.less'

export default function SelectTags({
  value,
  onChange,
  placeholder,
}: {
  value?: string[]
  onChange?: (val: string[]) => void
  placeholder?: string
}) {
  const [input, setInput] = useState('')

  const handleInputConfirm = () => {
    const trimmed = input.trim()
    if (trimmed && !value?.includes(trimmed)) {
      onChange?.([...(value ?? []), trimmed])
    }
    setInput('')
  }

  const handleClose = (removed: string) => {
    onChange?.(value?.filter((item) => item !== removed) ?? [])
  }

  return (
    <div>
      <div className={styles.tagList}>
        {value?.map((tag) => (
          <Tag key={tag} closable onClose={() => handleClose(tag)}>
            {tag}
          </Tag>
        ))}
      </div>
      <Input
        size="small"
        placeholder={placeholder}
        value={input}
        onBlur={handleInputConfirm}
        onChange={(event) => setInput(event.target.value)}
        onPressEnter={handleInputConfirm}
      />
    </div>
  )
}
