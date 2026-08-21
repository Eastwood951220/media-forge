import { Tag } from 'antd'
import { clsx } from 'clsx'
import type { StatusMeta } from '@/utils/status'
import { resolveStatusMeta } from '@/utils/status'

export interface StatusTagProps {
  status: string | undefined
  labels: Record<string, StatusMeta>
  fallbackText?: string
  className?: string
}

export function StatusTag({ status, labels, fallbackText, className }: StatusTagProps) {
  const meta = resolveStatusMeta(status, labels)
  return (
    <Tag className={clsx(className)} color={meta.color}>
      {meta.text === '-' && fallbackText ? fallbackText : meta.text}
    </Tag>
  )
}
