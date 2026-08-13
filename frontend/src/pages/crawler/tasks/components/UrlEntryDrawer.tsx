import { useEffect, useState } from 'react'
import { App, Button, Drawer, Form } from 'antd'
import { extractTaskName } from '@/api/crawlTask'
import type { TaskUrlEntry } from '@/api/crawlTask/types'
import {
  detectUrlSource,
  detectUrlType,
  type UrlType,
} from '../taskUrlUtils'
import UrlEntryFields from './UrlEntryFields'
import styles from '../TaskPages.module.less'

export type UrlEntryDrawerMode = 'create' | 'edit'

export interface UrlEntryDrawerSaveResult {
  entry: TaskUrlEntry
  extractedName?: string
}

export interface UrlEntryDrawerProps {
  open: boolean
  mode: UrlEntryDrawerMode
  initialValue?: TaskUrlEntry
  onCancel: () => void
  onSave: (result: UrlEntryDrawerSaveResult) => void
}

export default function UrlEntryDrawer({
  open,
  mode,
  initialValue,
  onCancel,
  onSave,
}: UrlEntryDrawerProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<{ urls: TaskUrlEntry[] }>()
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      urls: [
        initialValue ?? {
          url: '',
          url_type: '',
          has_magnet: true,
          has_chinese_sub: false,
          sort_type: 0,
          url_name: '',
        },
      ],
    })
  }, [form, initialValue, open])

  const handleSave = async () => {
    try {
      setSaving(true)
      const values = await form.validateFields()
      const entry = values.urls[0]
      const source = detectUrlSource(entry.url)
      const detected = detectUrlType(entry.url) || (source === 'javbus' ? 'detail' : null)
      const nextEntry: TaskUrlEntry = {
        ...entry,
        url_type: entry.url_type || detected || '',
        has_magnet: entry.has_magnet ?? false,
        has_chinese_sub: entry.has_chinese_sub ?? false,
        sort_type: entry.sort_type ?? 0,
        url_name: entry.url_name ?? '',
      }

      // Auto-fetch url_name if missing and we have a detectable type
      let extractedName: string | undefined
      if (!nextEntry.url_name && (detected || source)) {
        try {
          const result = await extractTaskName(nextEntry.url, (detected ?? 'detail') as UrlType)
          if (result.name?.trim()) {
            nextEntry.url_name = result.name.trim()
            extractedName = result.name.trim()
          } else {
            message.warning('未能自动获取 URL 名称')
          }
        } catch {
          message.warning('未能自动获取 URL 名称')
        }
      }

      onSave({ entry: nextEntry, extractedName })
    } catch {
      // Validation failed, form shows errors
    } finally {
      setSaving(false)
    }
  }

  return (
    <Drawer
      title={mode === 'create' ? '添加 URL' : '编辑 URL'}
      open={open}
      onClose={onCancel}
      width={600}
      className={styles.urlEntryDrawer}
      footer={
        <div className={styles.urlEntryDrawerFooter}>
          <Button onClick={onCancel} disabled={saving}>取消</Button>
          <Button type="primary" onClick={() => void handleSave()} loading={saving}>保存</Button>
        </div>
      }
    >
      <Form form={form} layout="vertical" disabled={saving}>
        <UrlEntryFields
          index={0}
          onNameExtracted={(index, name) => {
            form.setFieldValue(['urls', index, 'url_name'], name)
          }}
          onUrlTypeDetected={(index, urlType) => {
            form.setFieldValue(['urls', index, 'url_type'], urlType)
          }}
        />
      </Form>
    </Drawer>
  )
}