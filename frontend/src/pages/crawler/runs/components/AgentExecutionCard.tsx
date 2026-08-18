import { Button, Card, Empty, Space, Tag, Typography } from 'antd'
import { useRunAgentDiagnostics } from '../hooks/useRunAgentDiagnostics'
import AgentExecutionTimeline from './AgentExecutionTimeline'
import styles from '../RunDetailPage.module.less'

const MAX_ATTEMPTS = 3

export default function AgentExecutionCard({ runId }: { runId: string | undefined }) {
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
    >
      <Space style={{ marginBottom: 16 }} size={12} wrap>
        <Tag color="default">待领取 {summary.pending}</Tag>
        <Tag color="processing">执行中 {summary.active}</Tag>
        <Tag color="success">已完成 {summary.completed}</Tag>
        <Tag color="error">失败 {summary.failed}</Tag>
      </Space>

      {timelines.length === 0 ? (
        <Empty description="暂无 Agent 执行记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        timelines.map((timeline) =>
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
            <div key="unscoped" style={{ marginBottom: 16 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                运行级事件
              </Typography.Text>
              <AgentExecutionTimeline
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
            </div>
          ),
        )
      )}

      {hasNextPage && (
        <Button
          block
          onClick={() => void fetchNextPage()}
          loading={loadingMore}
          style={{ marginTop: 12 }}
        >
          加载更多
        </Button>
      )}
    </Card>
  )
}
