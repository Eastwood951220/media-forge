import { useMemo, useState } from 'react'
import { Card, Table } from 'antd'
import type { CrawlRunDetailTask, RunTaskSummary } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'
import RunTaskSummaryMetrics from './RunTaskSummaryMetrics'
import RunTaskToolbar from './RunTaskToolbar'
import { createRunTaskColumns } from './runTaskColumns'
import { confirmRetryAllFailed, confirmRetrySelected, confirmRetryTask } from '../utils/retryConfirm'

interface RunTaskTableProps {
  tasks: CrawlRunDetailTask[]
  loading: boolean
  statusFilter: string | undefined
  keyword: string
  pageSize: number
  current: number
  total: number
  summary: RunTaskSummary
  actionLoading: 'stop' | 'restart' | 'retry' | null
  runStatus: string | undefined
  onStatusChange: (value: string | undefined) => void
  onKeywordSearch: (value: string) => void
  onPageChange: (page: number, size: number) => void
  onRetryTask: (detailId: string) => Promise<void>
  onRetrySelected: (detailIds: string[]) => Promise<void>
  onRetryAllFailed: () => Promise<void>
}

function RunTaskTable({
  tasks,
  loading,
  statusFilter,
  keyword,
  pageSize,
  current,
  total,
  summary,
  actionLoading,
  runStatus,
  onStatusChange,
  onKeywordSearch,
  onPageChange,
  onRetryTask,
  onRetrySelected,
  onRetryAllFailed,
}: RunTaskTableProps) {
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const retryEnabled = runStatus === 'completed' || runStatus === 'failed' || runStatus === 'stopped'
  const failedTasks = useMemo(() => tasks.filter((task) => task.status === 'crawl_failed'), [tasks])
  const selectedFailedIds = selectedRowKeys.map(String)
  const clearSelection = () => setSelectedRowKeys([])
  const columns = useMemo(
    () => createRunTaskColumns({
      retryEnabled,
      actionLoading,
      onRetryTask: (detailId) => confirmRetryTask(detailId, onRetryTask, clearSelection),
    }),
    [retryEnabled, actionLoading, onRetryTask],
  )

  return (
    <Card
      title="子任务列表"
      style={{
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
      }}
    >
      <div className={styles.taskTableHeader}>
        <RunTaskSummaryMetrics summary={summary} />
        <RunTaskToolbar
          statusFilter={statusFilter}
          keyword={keyword}
          retryEnabled={retryEnabled}
          selectedFailedCount={selectedFailedIds.length}
          failedCount={failedTasks.length}
          actionLoading={actionLoading}
          onStatusChange={onStatusChange}
          onKeywordSearch={onKeywordSearch}
          onRetrySelected={() => confirmRetrySelected(selectedFailedIds, onRetrySelected, clearSelection)}
          onRetryAllFailed={() => confirmRetryAllFailed(failedTasks.length, onRetryAllFailed, clearSelection)}
        />
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        rowSelection={
          retryEnabled
            ? {
                selectedRowKeys,
                onChange: setSelectedRowKeys,
                getCheckboxProps: (record) => ({
                  disabled: record.status !== 'crawl_failed',
                }),
              }
            : undefined
        }
        pagination={{
          current,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100', '200'],
          showTotal: (count) => `共 ${count} 条`,
          onChange: onPageChange,
        }}
      />
    </Card>
  )
}

export default RunTaskTable
