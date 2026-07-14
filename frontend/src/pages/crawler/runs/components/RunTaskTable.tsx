import { useState } from 'react'
import { Button, Card, Input, Modal, Select, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import AnimatedNumber from '@/components/AnimatedNumber'
import type { CrawlRunDetailTask, RunTaskSummary } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'
import { runDetailStatusLabels } from '../utils/status'

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
  const failedTasks = tasks.filter((task) => task.status === 'crawl_failed')
  const selectedFailedIds = selectedRowKeys.map(String)

  const confirmRetryTask = (detailId: string) => {
    Modal.confirm({
      title: '重新爬取失败子任务',
      content: '确认重新爬取该失败子任务？',
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetryTask(detailId)
        setSelectedRowKeys([])
      },
    })
  }

  const confirmRetrySelected = () => {
    Modal.confirm({
      title: '重新爬取选中项',
      content: `确认重新爬取选中的 ${selectedFailedIds.length} 个失败子任务？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetrySelected(selectedFailedIds)
        setSelectedRowKeys([])
      },
    })
  }

  const confirmRetryAllFailed = () => {
    Modal.confirm({
      title: '重新爬取全部失败',
      content: `确认重新爬取全部 ${failedTasks.length} 个失败子任务？`,
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await onRetryAllFailed()
        setSelectedRowKeys([])
      },
    })
  }

  const columns: ColumnsType<CrawlRunDetailTask> = [
    {
      title: '番号',
      dataIndex: 'code',
      key: 'code',
      width: 120,
      render: (code: string) => (
        <span style={{ fontWeight: 500, fontFamily: 'var(--font-mono, monospace)' }}>{code}</span>
      ),
    },
    {
      title: '来源',
      dataIndex: 'source_name',
      key: 'source_name',
      ellipsis: true,
    },
    {
      title: 'URL来源',
      dataIndex: 'source_url_name',
      key: 'source_url_name',
      width: 140,
      ellipsis: true,
      render: (_, record) => record.source_url_name || record.task_url_type || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const { text, color } = runDetailStatusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '错误',
      dataIndex: 'error',
      key: 'error',
      ellipsis: true,
      render: (error: string | null) => error ? (
        <span style={{ color: '#dc2626', fontSize: 13 }}>{error}</span>
      ) : null,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) =>
        retryEnabled && record.status === 'crawl_failed' ? (
          <Button
            type="link"
            size="small"
            loading={actionLoading === 'retry'}
            onClick={() => confirmRetryTask(record.id)}
          >
            重新爬取
          </Button>
        ) : null,
    },
  ]

  return (
    <Card
      title="子任务列表"
      style={{
        borderRadius: 12,
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
      }}
    >
      <div className={styles.taskTableHeader}>
        <div className={styles.summaryMetrics}>
          <div className={`${styles.metricTile} ${styles.metricTotal}`}>
            <div className={styles.metricLabel}>总数</div>
            <div className={styles.metricValue}>
              <AnimatedNumber value={summary.total} duration={1.5} separator="," />
            </div>
          </div>
          <div className={`${styles.metricTile} ${styles.metricCompleted}`}>
            <div className={styles.metricLabel}>完成</div>
            <div className={styles.metricValue}>
              <AnimatedNumber value={summary.completed} duration={1.5} separator="," />
            </div>
          </div>
          <div className={`${styles.metricTile} ${styles.metricWaiting}`}>
            <div className={styles.metricLabel}>等待</div>
            <div className={styles.metricValue}>
              <AnimatedNumber value={summary.waiting} duration={1.5} separator="," />
            </div>
          </div>
          <div className={`${styles.metricTile} ${styles.metricSkipped}`}>
            <div className={styles.metricLabel}>跳过</div>
            <div className={styles.metricValue}>
              <AnimatedNumber value={summary.skipped} duration={1.5} separator="," />
            </div>
          </div>
          <div className={`${styles.metricTile} ${styles.metricFailed}`}>
            <div className={styles.metricLabel}>失败</div>
            <div className={styles.metricValue}>
              <AnimatedNumber value={summary.failed} duration={1.5} separator="," />
            </div>
          </div>
        </div>
        <div className={styles.filterSection}>
          <div className={styles.filterControls}>
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={(value) => onStatusChange(value)}
              options={Object.entries(runDetailStatusLabels).map(([key, { text }]) => ({
                value: key,
                label: text,
              }))}
            />
            <Input.Search
              placeholder="搜索番号或名称"
              allowClear
              value={keyword}
              onSearch={(value) => onKeywordSearch(value)}
              style={{ width: 200 }}
            />
          </div>
          <div className={styles.filterActions}>
            {retryEnabled && selectedFailedIds.length > 0 && (
              <Button loading={actionLoading === 'retry'} onClick={confirmRetrySelected}>
                重新爬取选中项 ({selectedFailedIds.length})
              </Button>
            )}
            {retryEnabled && failedTasks.length > 0 && (
              <Button
                type="primary"
                danger
                loading={actionLoading === 'retry'}
                onClick={confirmRetryAllFailed}
              >
                重新爬取全部失败 ({failedTasks.length})
              </Button>
            )}
          </div>
        </div>
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
