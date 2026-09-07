import { ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Card, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { StorageSubTask } from '@/api/storage/storageTasks/types'
import ResponsiveActions, { type ResponsiveAction } from '@/components/ResponsiveActions'
import styles from '../StorageTasks.module.less'
import { subTaskStatusLabels } from '../utils/status'

interface StorageSubTaskTableProps {
  subtasks: StorageSubTask[]
  loading: boolean
  onRetry?: (subtask: StorageSubTask) => void
  retryingSubtaskId?: string | null
}

export function StorageSubTaskTable({
  subtasks,
  loading,
  onRetry,
  retryingSubtaskId = null,
}: StorageSubTaskTableProps) {
  const navigate = useNavigate()

  const columns: ColumnsType<StorageSubTask> = [
    {
      title: '番号',
      dataIndex: 'movie_code',
      key: 'movie_code',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const { text, color } = subTaskStatusLabels[status] || { text: status, color: 'default' }
        return <Tag color={color}>{text}</Tag>
      },
    },
    {
      title: '步骤',
      dataIndex: 'step',
      key: 'step',
      width: 120,
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, record) => {
        const actions: ResponsiveAction[] = [
          {
            key: 'detail',
            label: '详情',
            onClick: () => void navigate({ to: `/storage/tasks/subtasks/${record.id}` }),
          },
          ...(record.status === 'failed' && onRetry
            ? [{
                key: 'retry',
                label: '重试',
                icon: <ReloadOutlined />,
                loading: retryingSubtaskId === record.id,
                onClick: () => void onRetry(record),
              }]
            : []),
        ]

        return <ResponsiveActions actions={actions} />
      },
    },
  ]

  return (
    <Card title="子任务明细" className={styles.subtaskTableCard}>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={subtasks}
        loading={loading}
        size="middle"
        scroll={{ x: 560 }}
        pagination={{
          pageSize: 50,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (count) => `共 ${count} 条`,
        }}
      />
    </Card>
  )
}
