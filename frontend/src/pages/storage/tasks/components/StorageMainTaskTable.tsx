import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Card, Progress, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { StorageMainTask, StorageMainTaskStatus, StorageMode } from '@/api/storage/storageTasks/types'
import ResponsiveActions, { type ResponsiveAction } from '@/components/ResponsiveActions'
import styles from '../StorageTasks.module.less'
import { modeLabels, PAGE_SIZE_OPTIONS, statusLabels } from '../utils/status'

interface StorageMainTaskTableProps {
  tasks: StorageMainTask[]
  loading: boolean
  total: number
  current: number
  pageSize: number
  hasMore?: boolean
  countLoading?: boolean
  onStop: (task: StorageMainTask) => void
  onRestart: (task: StorageMainTask) => void
  onDelete: (task: StorageMainTask) => void
  onRefresh: () => void
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

function getProgressPercent(task: StorageMainTask) {
  if (!task.total_count) return 0
  const finished = task.success_count + task.failed_count + task.skipped_count
  return Math.min(100, Math.round((finished / task.total_count) * 100))
}

export function StorageMainTaskTable({
  tasks,
  loading,
  total,
  current,
  pageSize,
  hasMore = false,
  countLoading = false,
  onStop,
  onRestart,
  onDelete,
  onRefresh,
  onPageChange,
  onPageSizeChange,
}: StorageMainTaskTableProps) {
  const navigate = useNavigate()

  const columns: ColumnsType<StorageMainTask> = [
    {
      title: '别名',
      dataIndex: 'alias',
      key: 'alias',
      ellipsis: true,
      render: (alias: string | null, record) => (
        <Typography.Text ellipsis title={alias || record.id}>
          {alias || record.id}
        </Typography.Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: StorageMainTaskStatus) => {
        const { text, color } = statusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '模式',
      dataIndex: 'storage_mode',
      key: 'storage_mode',
      width: 80,
      render: (mode: StorageMode) => modeLabels[mode] || mode,
    },
    {
      title: '处理进度',
      key: 'progress',
      width: 220,
      render: (_, record) => (
        <div className={styles.tableProgressCell}>
          <Progress
            percent={getProgressPercent(record)}
            size="small"
            status={record.failed_count > 0 ? 'exception' : undefined}
          />
          <div className={styles.tableProgressMeta}>
            <span>总 {record.total_count}</span>
            <span>成功 {record.success_count}</span>
            <span>失败 {record.failed_count}</span>
            <span>跳过 {record.skipped_count}</span>
          </div>
        </div>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (time: string | null) => (time ? new Date(time).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      fixed: 'right',
      width: 220,
      render: (_, record) => {
        const actions: ResponsiveAction[] = [
          {
            key: 'detail',
            label: '详情',
            icon: <EyeOutlined />,
            onClick: () => void navigate({ to: `/storage/tasks/${record.id}` }),
          },
          ...((record.status === 'queued' || record.status === 'running')
            ? [{
                key: 'stop',
                label: '停止',
                danger: true,
                icon: <StopOutlined />,
                onClick: () => void onStop(record),
              }]
            : []),
          ...((record.status === 'stopped' || record.status === 'failed')
            ? [{
                key: 'restart',
                label: '重启',
                type: 'primary' as const,
                icon: <ReloadOutlined />,
                onClick: () => void onRestart(record),
              }]
            : []),
          ...(!['queued', 'running', 'stopping'].includes(record.status)
            ? [{
                key: 'delete',
                label: '删除',
                danger: true,
                icon: <DeleteOutlined />,
                confirm: {
                  title: '删除存储任务',
                  description: '将删除主任务、子任务和对应日志，不会删除网盘文件。',
                  okText: '确定',
                  cancelText: '取消',
                },
                onClick: () => void onDelete(record),
              }]
            : []),
        ]

        return <ResponsiveActions actions={actions} />
      },
    },
  ]

  return (
    <Card
      title="任务列表"
      extra={(
        <Button
          icon={<ReloadOutlined />}
          onClick={() => void onRefresh()}
        >
          刷新
        </Button>
      )}
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        scroll={{ x: 980 }}
        pagination={{
          current,
          total: hasMore && !countLoading ? undefined : (countLoading ? 0 : total),
          pageSize,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showSizeChanger: true,
          showTotal: (count) => countLoading ? '统计中' : (count !== undefined ? `共 ${count} 条` : '统计中'),
          onChange: (page, size) => {
            onPageChange(page)
            onPageSizeChange(size)
          },
        }}
      />
    </Card>
  )
}
