import { Tag } from 'antd'
import { clsx } from 'clsx'
import type { ReactNode } from 'react'
import { formatTime } from '@/utils/datetime'
import styles from './LogList.module.less'

export interface LogEntry {
  id?: string
  timestamp: string
  level?: string
  source?: string
  message: ReactNode
}

export interface LogListProps {
  items: LogEntry[]
  levelColorMap?: Record<string, string>
  formatTime?: (value: string) => string
  height?: number | string
  className?: string
}

const DEFAULT_LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

export function LogList({
  items,
  levelColorMap = DEFAULT_LEVEL_COLORS,
  formatTime: formatTimeFn,
  height,
  className,
}: LogListProps) {
  return (
    <div
      className={clsx(styles.list, className)}
      style={height != null ? { height } : undefined}
    >
      {items.map((item, index) => (
        <div key={item.id ?? index} className={styles.row}>
          <span className={styles.time}>
            {formatTimeFn ? formatTimeFn(item.timestamp) : formatTime(item.timestamp)}
          </span>
          {item.level && (
            <Tag className={styles.level} color={levelColorMap[item.level] ?? 'default'}>
              {item.level}
            </Tag>
          )}
          {item.source && <span className={styles.source}>{item.source}</span>}
          <span className={styles.message}>{item.message}</span>
        </div>
      ))}
    </div>
  )
}
