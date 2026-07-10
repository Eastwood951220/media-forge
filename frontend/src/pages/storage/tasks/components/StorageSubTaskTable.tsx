import { useNavigate } from '@tanstack/react-router'
import { Button, Card, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { StorageSubTask } from '@/api/storage/storageTasks/types'
import styles from '../StorageTasks.module.less'
import { subTaskStatusLabels } from '../utils/status'

interface StorageSubTaskTableProps {
  subtasks: StorageSubTask[]
  loading: boolean
}

export function StorageSubTaskTable({ subtasks, loading }: StorageSubTaskTableProps) {
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
      width: 100,
      render: (_, record) => (
        <Button
          size="small"
          onClick={() => void navigate({ to: `/storage/tasks/subtasks/${record.id}` })}
        >
          详情
        </Button>
      ),
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
        scroll={{ x: 520 }}
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
