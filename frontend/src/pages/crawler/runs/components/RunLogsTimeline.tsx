import { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Empty, Spin, Tag, Typography } from 'antd'
import type { RunLogEntry } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

interface RunLogsTimelineProps {
  logs: RunLogEntry[]
  isActive: boolean
  loading?: boolean
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

function RunLogsTimeline({ logs, isActive, loading = false }: RunLogsTimelineProps) {
  const parentRef = useRef<HTMLDivElement | null>(null)
  const orderedLogs = useMemo(() => logs.slice().reverse(), [logs])
  const virtualizer = useVirtualizer({
    count: orderedLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
  })

  if (loading && orderedLogs.length === 0) {
    return (
      <div className={styles.loadingPlaceholder}>
        <Spin size="large" />
        <div className={styles.loadingText}>加载日志中...</div>
      </div>
    )
  }

  if (orderedLogs.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={isActive ? '等待日志...' : '无日志'}
      />
    )
  }

  return (
    <div
      ref={parentRef}
      role="list"
      aria-label="运行日志"
      className={styles.logContainer}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const entry = orderedLogs[virtualRow.index]
          return (
            <div
              key={`${entry.timestamp}-${virtualRow.index}`}
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
              <Typography.Text className={styles.logTime}>
                {formatTime(entry.timestamp)}
              </Typography.Text>
              <Tag color={levelColors[entry.level] || 'default'} className={styles.logTag}>
                {entry.level}
              </Tag>
              <Typography.Text
                type={entry.level === 'ERROR' ? 'danger' : undefined}
                className={styles.logMessage}
              >
                {entry.message}
              </Typography.Text>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default RunLogsTimeline
