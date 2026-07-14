import { useParams } from '@tanstack/react-router'
import { Card } from 'antd'
import RunLogsTimeline from './components/RunLogsTimeline'
import RunSummaryCard from './components/RunSummaryCard'
import RunTaskTable from './components/RunTaskTable'
import { useRunDetail } from './hooks/useRunDetail'
import { useRunDetailRealtime } from './hooks/useRunDetailRealtime'
import styles from './RunDetailPage.module.less'

function RunDetailPage() {
  const { id } = useParams({ strict: false })
  const detail = useRunDetail(id)

  useRunDetailRealtime({
    id,
    fetchLogs: detail.fetchLogs,
    fetchRun: detail.fetchRun,
    fetchTasks: detail.fetchTasks,
    fetchTaskSummary: detail.fetchTaskSummary,
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
        onRestart={detail.handleRestart}
        onStop={detail.handleStop}
        run={detail.run}
      />
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
        runStatus={detail.run?.status}
        statusFilter={detail.statusFilter}
        summary={detail.taskSummary}
        tasks={detail.tasks}
        total={detail.taskTotal}
      />
      {detail.run && (
        <Card
          title="运行日志"
          style={{
            borderRadius: 12,
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
          }}
        >
          <RunLogsTimeline
            logs={detail.logs}
            isActive={detail.run.status === 'queued' || detail.run.status === 'running'}
            loading={detail.loading}
          />
        </Card>
      )}
    </div>
  )
}

export default RunDetailPage
