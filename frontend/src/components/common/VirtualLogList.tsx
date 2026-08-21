import { useVirtualizer } from '@tanstack/react-virtual'
import { Empty, Spin, Tag } from 'antd'
import { useMemo, useRef, type ReactNode } from 'react'
import { formatTime } from '@/utils/datetime'
import styles from './LogList.module.less'

export interface VirtualLogEntry {
  id?: string
  timestamp: string
  level?: string
  source?: string
  message: ReactNode
}

export interface VirtualLogListProps {
  items: VirtualLogEntry[]
  height?: number | string
  levelColorMap?: Record<string, string>
  loading?: boolean
  emptyText?: string
  formatTime?: (value: string) => string
  className?: string
}

const DEFAULT_LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

export function VirtualLogList({
  items,
  height = 500,
  levelColorMap = DEFAULT_LEVEL_COLORS,
  loading = false,
  emptyText = '无日志',
  formatTime: formatTimeFn,
  className,
}: VirtualLogListProps) {
  const parentRef = useRef<HTMLDivElement | null>(null)
  const orderedLogs = useMemo(() => items.slice().reverse(), [items])
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual returns non-memoizable functions by design.
  const virtualizer = useVirtualizer({
    count: orderedLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
  })

  if (loading && orderedLogs.length === 0) {
    return (
      <div className={styles.loadingPlaceholder} style={{ height }}>
        <Spin size="large" />
        <div className={styles.loadingText}>加载日志中...</div>
      </div>
    )
  }

  if (orderedLogs.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
  }

  return (
    <div
      ref={parentRef}
      role="list"
      aria-label="日志"
      className={className ? `${styles.virtualContainer} ${className}` : styles.virtualContainer}
      style={{ height }}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const entry = orderedLogs[virtualRow.index]
          return (
            <div
              key={entry.id ?? `${entry.timestamp}-${virtualRow.index}`}
              ref={virtualizer.measureElement}
              data-index={virtualRow.index}
              role="listitem"
              className={styles.logItem}
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <span className={styles.logTime}>
                {formatTimeFn ? formatTimeFn(entry.timestamp) : formatTime(entry.timestamp)}
              </span>
              {entry.level && (
                <Tag color={levelColorMap[entry.level] ?? 'default'} className={styles.logTag}>
                  {entry.level}
                </Tag>
              )}
              {entry.source && <span className={styles.logSource}>{entry.source}</span>}
              <span className={styles.logMessage}>{entry.message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
