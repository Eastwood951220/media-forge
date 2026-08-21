import { useState } from 'react'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import { useParams } from '@tanstack/react-router'
import { Button, Card } from 'antd'
import AgentExecutionCard from './components/AgentExecutionCard'
import RunLogsTimeline from './components/RunLogsTimeline'
import RunSummaryCard from './components/RunSummaryCard'
import RunTaskSummaryMetrics from './components/RunTaskSummaryMetrics'
import RunTaskTable from './components/RunTaskTable'
import { useRunDetail } from './hooks/useRunDetail'
import { useRunDetailRealtime } from './hooks/useRunDetailRealtime'
import styles from './RunDetailPage.module.less'

function RunDetailPage() {
  const { id } = useParams({ strict: false })
  const detail = useRunDetail(id)
  const [logsExpanded, setLogsExpanded] = useState(true)

  useRunDetailRealtime({
    id,
    fetchTasks: detail.fetchTasks,
    keyword: detail.keyword,
    resyncSnapshot: detail.resyncSnapshot,
    setLogs: detail.setLogs,
    setRun: detail.setRun,
    setTaskSummary: detail.setTaskSummary,
    setTaskTotal: detail.setTaskTotal,
    setTasks: detail.setTasks,
    statusFilter: detail.statusFilter,
  })

  return (
    <div className={styles.page}>
      <RunSummaryCard
        actionLoading={detail.actionLoading}
        className={styles.sectionCard}
        onRestart={detail.handleRestart}
        onStop={detail.handleStop}
        run={detail.displayedRun}
      />
      <Card title="任务计数" className={styles.sectionCard}>
        <RunTaskSummaryMetrics summary={detail.taskSummary} />
      </Card>
      <RunTaskTable
        actionLoading={detail.actionLoading}
        current={detail.taskPage}
        keyword={detail.keyword}
        loading={detail.loading}
        onKeywordSearch={detail.handleKeywordSearch}
        onPageChange={detail.handleTaskPageChange}
        onRetryAllFailed={detail.handleRetryAllFailedTasks}
        onRetrySelected={detail.handleRetrySelectedTasks}
        onRetryTask={detail.handleRetryTask}
        onStatusChange={detail.handleStatusChange}
        pageSize={detail.pageSize}
        realtimeReady={detail.realtimeReady}
        runStatus={detail.displayedRun?.status}
        statusFilter={detail.statusFilter}
        tasks={detail.tasks}
        total={detail.taskTotal}
      />
      <AgentExecutionCard runId={id} />
      {detail.displayedRun && (
        <Card
          title="运行日志"
          className={styles.sectionCard}
          extra={
            <Button
              type="text"
              size="small"
              icon={logsExpanded ? <UpOutlined /> : <DownOutlined />}
              aria-label={logsExpanded ? '收起运行日志' : '展开运行日志'}
              onClick={() => setLogsExpanded((value) => !value)}
            />
          }
        >
          {logsExpanded && (
            <RunLogsTimeline
              logs={detail.logs}
              isActive={detail.displayedRun.status === 'queued' || detail.displayedRun.status === 'running'}
              loading={detail.loading}
            />
          )}
        </Card>
      )}
    </div>
  )
}

export default RunDetailPage
