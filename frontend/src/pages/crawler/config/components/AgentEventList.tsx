import { Button, Empty, List, Select, Spin } from 'antd'
import type { AgentEvent } from '@/api/crawler/crawlerAgent/types'
import { formatDateTime } from '@/utils/datetime'
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
      <div className={styles.agentEventFilters}>
        <Select
          allowClear
          placeholder="日志级别"
          className={styles.agentEventFilterSelect}
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
          className={styles.agentEventFilterSelect}
          value={sourceFilter}
          onChange={(value) => onSourceFilterChange(value ?? undefined)}
          options={[
            { value: 'backend', label: '后端' },
            { value: 'extension', label: '扩展' },
          ]}
        />
      </div>

      <div className={styles.agentEventViewport}>
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
                  <span className={styles.agentEventTime}>{formatDateTime(item.created_at)}</span>
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
          <Button block onClick={fetchNextPage} loading={loadingMore} className={styles.agentEventLoadMore}>
            查看更多
          </Button>
        )}
      </div>
    </div>
  )
}
