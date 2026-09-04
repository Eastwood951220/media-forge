import { useCallback, useMemo, useState } from 'react'
import { App, Button, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCrawlerSchedule,
  deleteCrawlerSchedule,
  disableCrawlerSchedule,
  enableCrawlerSchedule,
  getCrawlerSchedules,
  triggerCrawlerSchedule,
  updateCrawlerSchedule,
} from '@/api/crawler/crawlerSchedule'
import type {
  CrawlerSchedule,
  CrawlerSchedulePayload,
} from '@/api/crawler/crawlerSchedule/types'
import { getTaskDict } from '@/api/crawler/crawlTask'
import type { TaskDictItem } from '@/api/crawler/crawlTask/types'
import { queryKeys } from '@/api/queryKeys'
import { invalidateCrawlerSchedules } from '@/api/queryInvalidation'
import { MetricGrid, StatusTag } from '@/components/common'
import { formatDateTime } from '@/utils/datetime'
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import ScheduleFormDrawer from './components/ScheduleFormDrawer'
import ScheduleHistoryDrawer from './components/ScheduleHistoryDrawer'
import { formatRecurrence } from './utils/recurrence'
import styles from './SchedulePages.module.less'

const runStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '执行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  partial_failed: { text: '部分失败', color: 'warning' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'default' },
  skipped: { text: '已跳过', color: 'warning' },
}

const PAGE_SIZE_OPTIONS = ['10', '20', '50']

const storageModeLabels: Record<string, string> = {
  single: '单盘',
  multiple: '多盘',
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败'
}

function ScheduleListPage() {
  const queryClient = useQueryClient()
  const { message, modal } = App.useApp()

  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const listParams = useMemo(() => ({ page: current, size: pageSize }), [current, pageSize])

  const listQuery = useQuery({
    queryKey: queryKeys.crawlerSchedules.list(listParams),
    queryFn: () => getCrawlerSchedules(listParams),
    placeholderData: (previousData) => previousData,
  })

  const [formOpen, setFormOpen] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<CrawlerSchedule | null>(null)
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [historySchedule, setHistorySchedule] = useState<CrawlerSchedule | null>(null)
  const [taskOptions, setTaskOptions] = useState<TaskDictItem[]>([])
  const [taskOptionsLoading, setTaskOptionsLoading] = useState(false)
  const [triggeringId, setTriggeringId] = useState<string | null>(null)

  const rows = listQuery.data?.rows ?? []
  const total = listQuery.data?.total ?? 0

  const refreshList = useCallback(() => invalidateCrawlerSchedules(queryClient), [queryClient])

  useRouteActivationRefresh(refreshList)

  const loadTaskOptions = useCallback(async () => {
    setTaskOptionsLoading(true)
    try {
      setTaskOptions(await getTaskDict())
    } catch (error) {
      await message.error(getErrorMessage(error))
    } finally {
      setTaskOptionsLoading(false)
    }
  }, [message])

  const openCreate = useCallback(() => {
    setEditingSchedule(null)
    setFormOpen(true)
    void loadTaskOptions()
  }, [loadTaskOptions])

  const openEdit = useCallback((schedule: CrawlerSchedule) => {
    setEditingSchedule(schedule)
    setFormOpen(true)
    void loadTaskOptions()
  }, [loadTaskOptions])

  const handleSubmit = useCallback(async (payload: CrawlerSchedulePayload) => {
    setFormSubmitting(true)
    try {
      if (editingSchedule) {
        await updateCrawlerSchedule(editingSchedule.id, payload)
        await message.success('定时任务已更新')
      } else {
        await createCrawlerSchedule(payload)
        await message.success('定时任务已创建')
      }
      setFormOpen(false)
      await refreshList()
    } catch (error) {
      await message.error(getErrorMessage(error))
    } finally {
      setFormSubmitting(false)
    }
  }, [editingSchedule, message, refreshList])

  const handleToggleEnabled = useCallback(async (schedule: CrawlerSchedule) => {
    try {
      if (schedule.enabled) {
        await disableCrawlerSchedule(schedule.id)
        await message.success('定时任务已停用')
      } else {
        await enableCrawlerSchedule(schedule.id)
        await message.success('定时任务已启用')
      }
      await refreshList()
    } catch (error) {
      await message.error(getErrorMessage(error))
    }
  }, [message, refreshList])

  const handleTrigger = useCallback(async (scheduleId: string) => {
    setTriggeringId(scheduleId)
    try {
      const result = await triggerCrawlerSchedule(scheduleId)
      if (result.schedule_run_id) {
        await message.success('已触发执行')
      } else {
        await message.warning('已触发，但本次没有可执行内容')
      }
      await refreshList()
    } catch (error) {
      await message.error(getErrorMessage(error))
    } finally {
      setTriggeringId(null)
    }
  }, [message, refreshList])

  const handleDelete = useCallback((schedule: CrawlerSchedule) => {
    modal.confirm({
      title: '删除定时任务',
      content: `确定删除定时任务「${schedule.name}」吗？历史执行记录将一并删除。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteCrawlerSchedule(schedule.id)
          const currentRows = listQuery.data?.rows ?? []
          const nextPage = currentRows.length === 1 && current > 1 ? current - 1 : current
          await message.success('定时任务已删除')
          await refreshList()
          if (nextPage !== current) {
            setCurrent(nextPage)
          }
        } catch (error) {
          await message.error(getErrorMessage(error))
        }
      },
    })
  }, [current, listQuery.data, message, modal, refreshList])

  const enabledCount = rows.filter((row) => row.enabled).length

  const columns: ColumnsType<CrawlerSchedule> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
    },
    {
      title: '频率',
      key: 'frequency',
      width: 190,
      render: (_, record) => formatRecurrence(record.schedule_type, record.time_of_day, record.weekdays),
    },
    {
      title: '关联任务',
      key: 'tasks',
      width: 220,
      render: (_, record) => {
        const names = record.tasks.map((task) => task.name)
        if (names.length === 0) {
          return <span className={styles.muted}>—</span>
        }
        const text =
          names.length <= 2
            ? names.join('、')
            : `${names.slice(0, 2).join('、')} 等 ${record.task_count} 个`
        return (
          <span className={styles.taskNames} title={names.join('、')}>
            {text}
          </span>
        )
      },
    },
    {
      title: '下次执行',
      dataIndex: 'next_run_at',
      key: 'next_run_at',
      width: 170,
      render: (time: string | null) => (
        <span className={styles.muted}>{formatDateTime(time)}</span>
      ),
    },
    {
      title: '最近执行',
      key: 'last_run',
      width: 190,
      render: (_, record) => (
        <div className={styles.lastRunCell}>
          <span className={styles.muted}>{formatDateTime(record.last_triggered_at)}</span>
          {record.latest_run_status ? (
            <StatusTag status={record.latest_run_status} labels={runStatusLabels} />
          ) : null}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (enabled: boolean) =>
        enabled ? <Tag color="success">已启用</Tag> : <Tag>已停用</Tag>,
    },
    {
      title: '自动存储',
      key: 'auto_storage',
      width: 130,
      render: (_, record) =>
        record.auto_storage_enabled ? (
          <Space size={4}>
            <Tag color="processing">自动存储开</Tag>
            <span className={styles.muted}>
              {storageModeLabels[record.storage_mode] ?? record.storage_mode}
            </span>
          </Space>
        ) : (
          <Tag>自动存储关</Tag>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 280,
      render: (_, record) => (
        <Space size={4} wrap>
          <Button size="small" onClick={() => openEdit(record)}>编辑</Button>
          <Button size="small" onClick={() => void handleToggleEnabled(record)}>
            {record.enabled ? '停用' : '启用'}
          </Button>
          <Button
            size="small"
            loading={triggeringId === record.id}
            onClick={() => void handleTrigger(record.id)}
          >
            立即执行
          </Button>
          <Button size="small" onClick={() => setHistorySchedule(record)}>历史</Button>
          <Button size="small" danger onClick={() => handleDelete(record)}>删除</Button>
        </Space>
      ),
    },
  ]

  return (
    <div className={styles.page}>
      <section aria-label="定时任务统计">
        <MetricGrid
          items={[
            { key: 'total', label: '定时任务', value: total, tone: 'default' },
            { key: 'enabled', label: '已启用', value: enabledCount, tone: 'success' },
            { key: 'disabled', label: '已停用', value: rows.length - enabledCount, tone: 'warning' },
            {
              key: 'pending',
              label: '有待执行',
              value: rows.filter((row) => row.enabled && row.next_run_at).length,
              tone: 'info',
            },
          ]}
        />
      </section>

      <section className={styles.panel}>
        <div className={styles.toolbar}>
          <div>
            <h2 className={styles.toolbarTitle}>爬虫定时任务</h2>
            <p className={styles.toolbarSubtitle}>按固定时间自动执行选中的爬虫任务</p>
          </div>
          <Button type="primary" onClick={openCreate}>新建定时任务</Button>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={rows}
          loading={listQuery.isFetching}
          scroll={{ x: 1480 }}
          pagination={{
            current,
            pageSize,
            total,
            pageSizeOptions: PAGE_SIZE_OPTIONS,
            showSizeChanger: true,
            showTotal: (count) => `共 ${count} 条`,
            onChange: (page, size) => {
              setCurrent(page)
              setPageSize(size)
            },
          }}
        />
      </section>

      <ScheduleFormDrawer
        open={formOpen}
        editing={editingSchedule}
        taskOptions={taskOptions}
        taskOptionsLoading={taskOptionsLoading}
        submitting={formSubmitting}
        onCancel={() => setFormOpen(false)}
        onSubmit={handleSubmit}
      />

      {historySchedule ? (
        <ScheduleHistoryDrawer
          schedule={historySchedule}
          onClose={() => setHistorySchedule(null)}
        />
      ) : null}
    </div>
  )
}

export default ScheduleListPage
