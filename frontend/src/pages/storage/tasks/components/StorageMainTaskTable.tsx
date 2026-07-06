import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Card, Popconfirm, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { StorageMainTask, StorageMainTaskStatus, StorageMode } from '@/api/storage/storageTasks/types'
import { modeLabels, PAGE_SIZE_OPTIONS, statusLabels } from '../utils/status'

interface StorageMainTaskTableProps {
  tasks: StorageMainTask[]
  loading: boolean
  total: number
  current: number
  pageSize: number
  onStop: (task: StorageMainTask) => void
  onRestart: (task: StorageMainTask) => void
  onDelete: (task: StorageMainTask) => void
  onRefresh: () => void
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}

export function StorageMainTaskTable({
  tasks,
  loading,
  total,
  current,
  pageSize,
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
      title: '总数',
      dataIndex: 'total_count',
      key: 'total_count',
      width: 70,
      align: 'center',
    },
    {
      title: '成功',
      dataIndex: 'success_count',
      key: 'success_count',
      width: 70,
      align: 'center',
      render: (count: number) => <span style={{ color: '#52c41a' }}>{count}</span>,
    },
    {
      title: '失败',
      dataIndex: 'failed_count',
      key: 'failed_count',
      width: 70,
      align: 'center',
      render: (count: number) => (count > 0 ? <span style={{ color: '#ff4d4f' }}>{count}</span> : count),
    },
    {
      title: '跳过',
      dataIndex: 'skipped_count',
      key: 'skipped_count',
      width: 70,
      align: 'center',
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
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => void navigate({ to: `/storage/tasks/${record.id}` })}
          >
            详情
          </Button>
          {(record.status === 'queued' || record.status === 'running') && (
            <Button
              size="small"
              danger
              icon={<StopOutlined />}
              onClick={() => void onStop(record)}
            >
              停止
            </Button>
          )}
          {(record.status === 'stopped' || record.status === 'failed') && (
            <Button
              size="small"
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => void onRestart(record)}
            >
              重启
            </Button>
          )}
          {!['queued', 'running', 'stopping'].includes(record.status) && (
            <Popconfirm
              title="删除存储任务"
              description="将删除主任务、子任务和对应日志，不会删除网盘文件。"
              okText="确定"
              cancelText="取消"
              onConfirm={() => void onDelete(record)}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="存储任务"
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
        pagination={{
          current,
          total,
          pageSize,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          showSizeChanger: true,
          showTotal: (count) => `共 ${count} 条`,
          onChange: (page, size) => {
            onPageChange(page)
            onPageSizeChange(size)
          },
        }}
      />
    </Card>
  )
}
