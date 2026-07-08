import { useParams } from '@tanstack/react-router'
import { Card } from 'antd'
import RunLogsTimeline from './components/RunLogsTimeline'
import RunSummaryCard from './components/RunSummaryCard'
import RunTaskTable from './components/RunTaskTable'
import { useRunDetail } from './hooks/useRunDetail'
import { useRunDetailRealtime } from './hooks/useRunDetailRealtime'

function RunDetailPage() {
  const { id } = useParams({ strict: false })
  const detail = useRunDetail(id)

  useRunDetailRealtime({
    id,
    fetchLogs: detail.fetchLogs,
    fetchTasks: detail.fetchTasks,
    keyword: detail.keyword,
    resyncSnapshot: detail.resyncSnapshot,
    setLogs: detail.setLogs,
    setRun: detail.setRun,
    setTasks: detail.setTasks,
    statusFilter: detail.statusFilter,
  })

  return (
    <div style={{ padding: 24 }}>
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
        <Card title="运行日志" style={{ marginTop: 16 }}>
          <RunLogsTimeline
            logs={detail.logs}
            isActive={detail.run.status === 'queued' || detail.run.status === 'running'}
          />
        </Card>
      )}
    </div>
  )
}

export default RunDetailPage
