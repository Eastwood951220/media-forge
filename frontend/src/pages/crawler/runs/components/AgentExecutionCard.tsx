import { useState } from 'react'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import { Button, Card, Empty } from 'antd'
import { useRunAgentDiagnostics } from '../hooks/useRunAgentDiagnostics'
import AgentExecutionTimeline from './AgentExecutionTimeline'
import styles from '../RunDetailPage.module.less'

const MAX_ATTEMPTS = 3

export default function AgentExecutionCard({ runId }: { runId: string | undefined }) {
  const [expanded, setExpanded] = useState(true)
  const {
    summary,
    timelines,
    loading,
    hasNextPage,
    fetchNextPage,
    loadingMore,
    hasDiagnostics,
  } = useRunAgentDiagnostics(runId)

  if (!hasDiagnostics && !loading) {
    return null
  }

  return (
    <Card
      title="Agent 执行时间线"
      className={styles.agentExecutionCard}
      loading={loading}
      extra={
        <Button
          type="text"
          size="small"
          icon={expanded ? <UpOutlined /> : <DownOutlined />}
          aria-label={expanded ? '收起 Agent 执行时间线' : '展开 Agent 执行时间线'}
          onClick={() => setExpanded((value) => !value)}
        />
      }
    >
      <div className={styles.agentTimelineSummary}>
        <div className={`${styles.agentTimelineMetric} ${styles.agentTimelineMetricPending}`}>
          <span className={styles.agentTimelineMetricLabel}>待领取</span>
          <span className={styles.agentTimelineMetricValue}>{summary.pending}</span>
        </div>
        <div className={`${styles.agentTimelineMetric} ${styles.agentTimelineMetricActive}`}>
          <span className={styles.agentTimelineMetricLabel}>执行中</span>
          <span className={styles.agentTimelineMetricValue}>{summary.active}</span>
        </div>
        <div className={`${styles.agentTimelineMetric} ${styles.agentTimelineMetricCompleted}`}>
          <span className={styles.agentTimelineMetricLabel}>已完成</span>
          <span className={styles.agentTimelineMetricValue}>{summary.completed}</span>
        </div>
        <div className={`${styles.agentTimelineMetric} ${styles.agentTimelineMetricFailed}`}>
          <span className={styles.agentTimelineMetricLabel}>失败</span>
          <span className={styles.agentTimelineMetricValue}>{summary.failed}</span>
        </div>
      </div>

      {expanded && (
        timelines.length === 0 ? (
          <Empty description="暂无 Agent 执行记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className={styles.agentTimelineGroup}>
            {timelines.map((timeline) =>
              timeline.workItem ? (
                <AgentExecutionTimeline
                  key={timeline.workItem.id}
                  events={timeline.events}
                  workItemId={timeline.workItem.id}
                  url={timeline.workItem.url}
                  pageKind={timeline.workItem.page_kind}
                  status={timeline.workItem.status}
                  attempt={timeline.workItem.attempt}
                  maxAttempts={MAX_ATTEMPTS}
                  errorReason={timeline.workItem.error_reason}
                  startedAt={timeline.workItem.started_at}
                  finishedAt={timeline.workItem.finished_at}
                />
              ) : (
                <AgentExecutionTimeline
                  key="unscoped"
                  events={timeline.events}
                  workItemId="-"
                  url=""
                  pageKind=""
                  status=""
                  attempt={0}
                  maxAttempts={MAX_ATTEMPTS}
                  errorReason={null}
                  startedAt={null}
                  finishedAt={null}
                />
              ),
            )}
          </div>
        )
      )}

      {expanded && hasNextPage && (
        <Button
          block
          onClick={() => void fetchNextPage()}
          loading={loadingMore}
          className={styles.agentTimelineLoadMore}
        >
          加载更多
        </Button>
      )}
    </Card>
  )
}
