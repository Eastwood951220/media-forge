import { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Empty, Tag, Typography } from 'antd'
import type { RunLogEntry } from '@/api/crawlerRun/types'

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

interface RunLogsTimelineProps {
  logs: RunLogEntry[]
  isActive: boolean
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

function RunLogsTimeline({ logs, isActive }: RunLogsTimelineProps) {
  const parentRef = useRef<HTMLDivElement | null>(null)
  const orderedLogs = useMemo(() => logs.slice().reverse(), [logs])
  const virtualizer = useVirtualizer({
    count: orderedLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
  })

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
      style={{ height: 500, overflow: 'auto', paddingRight: 8 }}
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
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                display: 'grid',
                gridTemplateColumns: '88px 88px minmax(0, 1fr)',
                gap: 8,
                alignItems: 'start',
                minHeight: 40,
                padding: '6px 0',
                borderBottom: '1px solid rgba(5, 5, 5, 0.06)',
              }}
            >
              <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: '24px' }}>
                {formatTime(entry.timestamp)}
              </Typography.Text>
              <Tag color={levelColors[entry.level] || 'default'} style={{ width: 78, textAlign: 'center', marginInlineEnd: 0 }}>
                {entry.level}
              </Tag>
              <Typography.Text
                type={entry.level === 'ERROR' ? 'danger' : undefined}
                style={{ wordBreak: 'break-word' }}
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
