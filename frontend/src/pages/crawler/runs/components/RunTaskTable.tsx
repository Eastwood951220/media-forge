import { useMemo, useState } from 'react'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import { Button, Card, Table } from 'antd'
import type { CrawlRunDetailTask } from '@/api/crawler/crawlerRun/types'
import styles from '../RunDetailPage.module.less'
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
  actionLoading: 'stop' | 'restart' | 'retry' | null
  realtimeReady: boolean
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
  actionLoading,
  realtimeReady,
  runStatus,
  onStatusChange,
  onKeywordSearch,
  onPageChange,
  onRetryTask,
  onRetrySelected,
  onRetryAllFailed,
}: RunTaskTableProps) {
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [expanded, setExpanded] = useState(true)
  const retryEnabled = runStatus === 'completed' || runStatus === 'failed' || runStatus === 'stopped'
  const failedTasks = useMemo(() => tasks.filter((task) => task.status === 'crawl_failed'), [tasks])
  const selectedFailedIds = selectedRowKeys.map(String)
  const clearSelection = () => setSelectedRowKeys([])
  const columns = useMemo(
    () => createRunTaskColumns({
      retryEnabled,
      realtimeReady,
      actionLoading,
      onRetryTask: (detailId) => confirmRetryTask(detailId, onRetryTask, clearSelection),
    }),
    [retryEnabled, realtimeReady, actionLoading, onRetryTask],
  )

  return (
    <Card
      title="子任务列表"
      className={styles.sectionCard}
      extra={
        <Button
          type="text"
          size="small"
          icon={expanded ? <UpOutlined /> : <DownOutlined />}
          aria-label={expanded ? '收起子任务列表' : '展开子任务列表'}
          onClick={() => setExpanded((value) => !value)}
        />
      }
    >
      {expanded && (
        <>
          <div className={styles.taskTableToolbarRow}>
            <RunTaskToolbar
              statusFilter={statusFilter}
              keyword={keyword}
              retryEnabled={retryEnabled}
              selectedFailedCount={selectedFailedIds.length}
              failedCount={failedTasks.length}
              actionLoading={actionLoading}
              onStatusChange={onStatusChange}
              onKeywordSearch={onKeywordSearch}
              onRetrySelected={() =>
                confirmRetrySelected(selectedFailedIds, onRetrySelected, clearSelection)
              }
              onRetryAllFailed={() =>
                confirmRetryAllFailed(failedTasks.length, onRetryAllFailed, clearSelection)
              }
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
        </>
      )}
    </Card>
  )
}

export default RunTaskTable
