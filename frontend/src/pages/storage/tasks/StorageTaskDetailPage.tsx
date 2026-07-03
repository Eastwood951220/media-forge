import { useCallback, useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { Button, Card, Descriptions, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  getStorageMainTask,
  listStorageSubTasks,
  restartStorageMainTask,
  stopStorageMainTask,
} from '@/api/storage/storageTasks'
import type { StorageMainTask, StorageMode, StorageSubTask } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent } from '@/realtime/types'
import { useNavigate } from '@tanstack/react-router'
import styles from './StorageTasks.module.less'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  stopping: { text: '停止中', color: 'warning' },
  stopped: { text: '已停止', color: 'warning' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}

const subTaskStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

const modeLabels: Record<StorageMode, string> = {
  single: '单盘',
  multiple: '多盘',
}

function StorageTaskDetailPage() {
  const { id } = useParams({ strict: false })
  const navigate = useNavigate()
  const [task, setTask] = useState<StorageMainTask | null>(null)
  const [subtasks, setSubtasks] = useState<StorageSubTask[]>([])
  const [loading, setLoading] = useState(false)
  const [subtasksLoading, setSubtasksLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<'stop' | 'restart' | null>(null)

  const fetchTask = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getStorageMainTask(id)
      setTask(data)
    } finally {
      setLoading(false)
    }
  }, [id])

  const fetchSubtasks = useCallback(async () => {
    if (!id) return
    setSubtasksLoading(true)
    try {
      const data = await listStorageSubTasks(id, { limit: 200 })
      setSubtasks(data.rows)
    } finally {
      setSubtasksLoading(false)
    }
  }, [id])

  useEffect(() => {
    setTask(null)
    setSubtasks([])
  }, [id])

  useEffect(() => {
    void fetchTask()
  }, [fetchTask])

  useEffect(() => {
    void fetchSubtasks()
  }, [fetchSubtasks])

  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeTask = subscribeRealtime<StorageMainTask>(
      'storage.main.updated',
      (event: RealtimeEvent<StorageMainTask>) => {
        if (event.payload.id !== id) return
        setTask((current) => (current ? { ...current, ...event.payload } : event.payload))
      },
    )

    const unsubscribeSubtask = subscribeRealtime<StorageSubTask[]>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubTask[]>) => {
        if (!Array.isArray(event.payload)) return
        setSubtasks((current) => {
          const byId = new Map(current.map((st) => [st.id, st]))
          for (const subtask of event.payload) {
            if (subtask.main_task_id === id) {
              byId.set(subtask.id, subtask)
            }
          }
          return Array.from(byId.values())
        })
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        void fetchTask()
        void fetchSubtasks()
      },
    )

    return () => {
      unsubscribeTask()
      unsubscribeSubtask()
      unsubscribeResync()
    }
  }, [id, fetchTask, fetchSubtasks])

  const handleStop = useCallback(async () => {
    if (!id) return
    setActionLoading('stop')
    try {
      const stoppedTask = await stopStorageMainTask(id)
      setTask(stoppedTask)
      void fetchSubtasks()
    } catch {
      // error handled by request interceptor
    } finally {
      setActionLoading(null)
    }
  }, [id, fetchSubtasks])

  const handleRestart = useCallback(async () => {
    if (!id) return
    setActionLoading('restart')
    try {
      const restartedTask = await restartStorageMainTask(id)
      setTask(restartedTask)
      void fetchSubtasks()
    } catch {
      // error handled by request interceptor
    } finally {
      setActionLoading(null)
    }
  }, [id, fetchSubtasks])

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
    <div className={styles.page}>
      {task && (
        <Card
          title={`存储任务详情 - ${task.alias || task.id}`}
          extra={(
            <Space>
              {(task.status === 'queued' || task.status === 'running') && (
                <Button
                  danger
                  icon={<StopOutlined />}
                  loading={actionLoading === 'stop'}
                  onClick={() => void handleStop()}
                >
                  停止
                </Button>
              )}
              {(task.status === 'stopped' || task.status === 'failed') && (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  loading={actionLoading === 'restart'}
                  onClick={() => void handleRestart()}
                >
                  重启
                </Button>
              )}
            </Space>
          )}
          style={{ marginBottom: 16 }}
          loading={loading}
        >
          <Descriptions column={3}>
            <Descriptions.Item label="别名">{task.alias || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={statusLabels[task.status]?.color}>{statusLabels[task.status]?.text || task.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="模式">{modeLabels[task.storage_mode] || task.storage_mode}</Descriptions.Item>
            <Descriptions.Item label="总数">{task.total_count}</Descriptions.Item>
            <Descriptions.Item label="成功">
              <span style={{ color: '#52c41a' }}>{task.success_count}</span>
            </Descriptions.Item>
            <Descriptions.Item label="失败">
              {task.failed_count > 0 ? (
                <span style={{ color: '#ff4d4f' }}>{task.failed_count}</span>
              ) : (
                task.failed_count
              )}
            </Descriptions.Item>
            <Descriptions.Item label="跳过">{task.skipped_count}</Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {task.created_at ? new Date(task.created_at).toLocaleString() : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="完成时间">
              {task.finished_at ? new Date(task.finished_at).toLocaleString() : '-'}
            </Descriptions.Item>
            {task.error_message && (
              <Descriptions.Item label="错误信息" span={3}>
                {task.error_message}
              </Descriptions.Item>
            )}
          </Descriptions>
        </Card>
      )}

      <Card title="子任务列表">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={subtasks}
          loading={subtasksLoading}
          pagination={{
            pageSize: 50,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (count) => `共 ${count} 条`,
          }}
        />
      </Card>
    </div>
  )
}

export default StorageTaskDetailPage
