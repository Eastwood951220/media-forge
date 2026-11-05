import { useEffect, useRef, useState } from 'react'
import { App, Input } from 'antd'
import type { PasswordProps } from 'antd/es/input'

type Props = Omit<PasswordProps, 'visibilityToggle'> & {
  configured: boolean
  loadSavedValue: () => Promise<{ value: string }>
}

/** Viewing a saved secret never changes the form's editable value. */
export function SavedSecretInput({ configured, loadSavedValue, value, onChange, ...props }: Props) {
  const { message } = App.useApp()
  const [visible, setVisible] = useState(false)
  const [saved, setSaved] = useState<{ value: string; source: typeof value } | null>(null)
  const [loading, setLoading] = useState(false)
  const requestId = useRef(0)
  const latestValue = useRef(value)
  latestValue.current = value
  useEffect(() => () => { requestId.current++ }, [])

  const toggle = async (next: boolean) => {
    const id = ++requestId.current
    if (!next) {
      setVisible(false)
      setSaved(null)
      setLoading(false)
      return
    }
    if (value || !configured) { setVisible(true); return }
    setLoading(true)
    try {
      const result = await loadSavedValue()
      if (id !== requestId.current || latestValue.current !== value) return
      setSaved({ value: result.value, source: value })
      setVisible(true)
    } catch {
      if (id === requestId.current) message.error('无法读取已保存的值，请重试')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  return <Input.Password {...props} value={(saved && saved.source === value ? saved.value : value) ?? ''}
    aria-busy={loading} placeholder={loading ? '正在读取…' : props.placeholder}
    visibilityToggle={{ visible, onVisibleChange: next => { void toggle(next) } }}
    onChange={event => {
      requestId.current++
      setLoading(false)
      setSaved(null)
      onChange?.(event)
    }} />
}
