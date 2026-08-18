import { Button, Empty, List, Select, Space, Spin } from 'antd'
import type { AgentEvent } from '@/api/crawler/crawlerAgent/types'
import styles from '../ConfigPage.module.less'

interface AgentEventListProps {
  events: AgentEvent[]
  loading: boolean
  levelFilter?: string
  onLevelFilterChange: (value: string | undefined) => void
  sourceFilter?: string
  onSourceFilterChange: (value: string | undefined) => void
  hasNextPage: boolean
  fetchNextPage: () => void
  loadingMore: boolean
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

export default function AgentEventList({
  events,
  loading,
  levelFilter,
  onLevelFilterChange,
  sourceFilter,
  onSourceFilterChange,
  hasNextPage,
  fetchNextPage,
  loadingMore,
}: AgentEventListProps) {
  return (
    <div className={styles.agentEventList}>
      <Space style={{ marginBottom: 8 }} wrap>
        <Select
          allowClear
          placeholder="日志级别"
          style={{ width: 120 }}
          value={levelFilter}
          onChange={(value) => onLevelFilterChange(value ?? undefined)}
          options={[
            { value: 'info', label: '信息' },
            { value: 'warning', label: '警告' },
            { value: 'error', label: '错误' },
          ]}
        />
        <Select
          allowClear
          placeholder="来源"
          style={{ width: 120 }}
          value={sourceFilter}
          onChange={(value) => onSourceFilterChange(value ?? undefined)}
          options={[
            { value: 'backend', label: '后端' },
            { value: 'extension', label: '扩展' },
          ]}
        />
      </Space>

      {loading && events.length === 0 ? (
        <div className={styles.agentEventEmpty}>
          <Spin size="small" />
        </div>
      ) : events.length === 0 ? (
        <Empty description="暂无诊断日志" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={events}
          renderItem={(item) => (
            <List.Item>
              <div className={styles.agentEventRow}>
                <span className={styles.agentEventTime}>{formatTime(item.created_at)}</span>
                <span className={styles.agentEventLevel}>
                  {item.level === 'error' ? '错误' : item.level === 'warning' ? '警告' : '信息'}
                </span>
                <span className={styles.agentEventMessage}>{item.message}</span>
              </div>
            </List.Item>
          )}
        />
      )}

      {hasNextPage && (
        <Button block onClick={fetchNextPage} loading={loadingMore} style={{ marginTop: 8 }}>
          查看更多
        </Button>
      )}
    </div>
  )
}
