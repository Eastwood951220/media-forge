import { useCallback, useEffect, useState } from 'react'
import { DeleteOutlined, EyeOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Card, Popconfirm, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  deleteStorageMainTask,
  listStorageMainTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
import type { StorageMainTask, StorageMainTaskStatus, StorageMode } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent, StorageMainDeletedPayload } from '@/realtime/types'
import styles from './StorageTasks.module.less'

const statusLabels: Record<StorageMainTaskStatus, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  stopping: { text: '停止中', color: 'warning' },
  stopped: { text: '已停止', color: 'warning' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}

const modeLabels: Record<StorageMode, string> = {
  single: '单盘',
  multiple: '多盘',
}

const PAGE_SIZE_OPTIONS = ['10', '20', '50']

function StorageTaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<StorageMainTask[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const fetchTasks = useCallback(async (page: number, size: number) => {
    setLoading(true)
    try {
      const data = await listStorageMainTasks({ page, limit: size })
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks(current, pageSize)
  }, [current, pageSize, fetchTasks])

  useEffect(() => {
    connectRealtime()

    const unsubscribeUpdated = subscribeRealtime<StorageMainTask>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainTask>) => {
        const updatedTask = event.payload
        setTasks((prev) =>
          prev.map((task) =>
            task.id === updatedTask.id ? { ...task, ...updatedTask } : task,
          ),
        )
      },
    )

    const unsubscribeDeleted = subscribeRealtime<StorageMainDeletedPayload>(
      'storage.main.deleted',
      (event: RealtimeEvent<StorageMainDeletedPayload>) => {
        setTasks((prev) => prev.filter((task) => task.id !== event.payload.id))
        setTotal((count) => Math.max(0, count - 1))
      },
    )

    return () => {
      unsubscribeUpdated()
      unsubscribeDeleted()
    }
  }, [])

  const handleStop = useCallback(async (task: StorageMainTask) => {
    try {
      await stopStorageMainTask(task.id)
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, pageSize, fetchTasks])

  const handleRestart = useCallback(async (task: StorageMainTask) => {
    try {
      await restartStorageMainTask(task.id)
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, pageSize, fetchTasks])

  const handleDelete = useCallback(async (task: StorageMainTask) => {
    try {
      await deleteStorageMainTask(task.id)
      if (tasks.length === 1 && current > 1) {
        setCurrent((page) => page - 1)
        return
      }
      void fetchTasks(current, pageSize)
    } catch {
      // error handled by request interceptor
    }
  }, [current, fetchTasks, pageSize, tasks.length])

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
              onClick={() => void handleStop(record)}
            >
              停止
            </Button>
          )}
          {(record.status === 'stopped' || record.status === 'failed') && (
            <Button
              size="small"
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => void handleRestart(record)}
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
              onConfirm={() => void handleDelete(record)}
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
    <div className={styles.page}>
      <Card
        title="存储任务"
        extra={(
          <Button
            icon={<ReloadOutlined />}
            onClick={() => void fetchTasks(current, pageSize)}
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
              setCurrent(page)
              setPageSize(size)
            },
          }}
        />
      </Card>
    </div>
  )
}

export default StorageTaskListPage
