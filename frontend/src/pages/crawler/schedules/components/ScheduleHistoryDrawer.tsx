import { useMemo, useState } from 'react'
import { Drawer, Empty, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { getCrawlerScheduleRuns } from '@/api/crawler/crawlerSchedule'
import type { CrawlerSchedule, CrawlerScheduleRun } from '@/api/crawler/crawlerSchedule/types'
import { queryKeys } from '@/api/queryKeys'
import { StatusTag } from '@/components/common'
import { formatDateTime } from '@/utils/datetime'
import styles from '../SchedulePages.module.less'

const runStatusLabels: Record<string, { text: string; color: string }> = {
  running: { text: '执行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  partial_failed: { text: '部分失败', color: 'warning' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'default' },
  skipped: { text: '已跳过', color: 'warning' },
}

const triggerTypeLabels: Record<string, { text: string; color: string }> = {
  scheduled: { text: '定时', color: 'blue' },
  manual: { text: '手动', color: 'orange' },
}

const storageStatusLabels: Record<string, { text: string; color: string }> = {
  disabled: { text: '未启用', color: 'default' },
  pending: { text: '待处理', color: 'warning' },
  created: { text: '已创建', color: 'success' },
  skipped: { text: '已跳过', color: 'default' },
  failed: { text: '失败', color: 'error' },
}

interface ScheduleHistoryDrawerProps {
  schedule: CrawlerSchedule
  onClose: () => void
}

export default function ScheduleHistoryDrawer({ schedule, onClose }: ScheduleHistoryDrawerProps) {
  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])

  const runsQuery = useQuery({
    queryKey: queryKeys.crawlerSchedules.runs(schedule.id, listParams),
    queryFn: () => getCrawlerScheduleRuns(schedule.id, listParams),
    placeholderData: (previousData) => previousData,
  })

  const rows = runsQuery.data?.rows ?? []
  const loading = runsQuery.isFetching

  const columns: ColumnsType<CrawlerScheduleRun> = [
    {
      title: '触发时间',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      width: 170,
      render: (time: string) => (
        <span className={styles.historyTime}>{formatDateTime(time)}</span>
      ),
    },
    {
      title: '触发方式',
      dataIndex: 'trigger_type',
      key: 'trigger_type',
      width: 100,
      render: (triggerType: string) => {
        const label = triggerTypeLabels[triggerType]
        return label ? <Tag color={label.color}>{label.text}</Tag> : <Tag>{triggerType}</Tag>
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) => (
        <StatusTag status={status} labels={runStatusLabels} fallbackText="未知" />
      ),
    },
    {
      title: '结果',
      key: 'result',
      width: 160,
      render: (_, record) => {
        const result = record.result ?? {}
        const accepted = Array.isArray(result.accepted) ? result.accepted.length : 0
        const skipped = Array.isArray(result.skipped) ? result.skipped.length : 0
        const failed = Array.isArray(result.failed) ? result.failed.length : 0
        if (accepted === 0 && skipped === 0 && failed === 0) {
          return <span className={styles.muted}>{result.reason ?? '—'}</span>
        }
        return <span>成功 {accepted} · 跳过 {skipped} · 失败 {failed}</span>
      },
    },
    {
      title: '关联爬取',
      key: 'crawl_runs',
      width: 150,
      render: (_, record) => {
        const runIds = record.crawl_run_ids ?? []
        if (runIds.length === 0) {
          return <span className={styles.muted}>—</span>
        }
        return (
          <span className={styles.historyRunLinks}>
            {runIds.map((runId) => (
              <Link key={runId} to="/crawler/runs/$id" params={{ id: runId }} title={runId}>
                {runId.slice(0, 8)}
              </Link>
            ))}
          </span>
        )
      },
    },
    {
      title: '存储任务',
      key: 'storage',
      width: 130,
      render: (_, record) => {
        if (record.storage_task_id) {
          return (
            <Link to="/storage/tasks/$id" params={{ id: record.storage_task_id }}>
              查看
            </Link>
          )
        }
        const label = storageStatusLabels[record.storage_status]
        return label ? <Tag color={label.color}>{label.text}</Tag> : <span className={styles.muted}>—</span>
      },
    },
  ]

  return (
    <Drawer
      title={`执行历史：${schedule.name}`}
      placement="right"
      size={760}
      open
      onClose={onClose}
    >
      <div className={styles.historyBody}>
        {rows.length === 0 && !loading ? (
          <Empty description="暂无执行记录" />
        ) : (
          <Table
            size="small"
            rowKey="id"
            columns={columns}
            dataSource={rows}
            loading={loading}
            scroll={{ x: 820 }}
            pagination={{
              current,
              pageSize,
              total: runsQuery.data?.total ?? 0,
              showSizeChanger: false,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, size) => {
                setCurrent(page)
                setPageSize(size)
              },
            }}
          />
        )}
      </div>
    </Drawer>
  )
}
