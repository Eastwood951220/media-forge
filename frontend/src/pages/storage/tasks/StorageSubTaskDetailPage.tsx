import { useCallback, useEffect, useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { Card, Descriptions, Empty, Tag, Timeline, Typography } from 'antd'
import { getStorageSubTask, getStorageSubTaskLogs } from '@/api/storage/storageTasks'
import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'
import { connectRealtime, subscribeRealtime } from '@/realtime/eventSourceClient'
import type { RealtimeEvent } from '@/realtime/types'
import styles from './StorageTasks.module.less'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  skipped: { text: '已跳过', color: 'default' },
}

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'processing',
  WARNING: 'warning',
  ERROR: 'error',
}

const stepOrder = [
  'prepare',
  'submit_magnet',
  'waiting_download',
  'scan_files',
  'select_videos',
  'rename_files',
  'move_files',
  'verify_result',
  'cleanup_files',
]

const stepLabels: Record<string, string> = {
  prepare: '准备任务',
  submit_magnet: '提交磁力',
  waiting_download: '云端下载',
  scan_files: '扫描文件',
  select_videos: '识别主视频',
  rename_files: '重命名',
  move_files: '移动文件',
  verify_result: '校验结果',
  cleanup_files: '清理临时文件',
}

function logsForStep(logs: StorageTaskLog[], step: string) {
  return logs.filter((log) => log.step === step || log.context?.step === step)
}

function stepColor(subtask: StorageSubTask, logs: StorageTaskLog[], step: string) {
  if (logs.some((log) => log.level === 'ERROR')) return 'red'
  if (logs.length > 0) return 'green'
  if (subtask.step === step) return 'blue'
  return 'gray'
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString()
}

function StorageSubTaskDetailPage() {
  const { id } = useParams({ strict: false })
  const [subtask, setSubtask] = useState<StorageSubTask | null>(null)
  const [logs, setLogs] = useState<StorageTaskLog[]>([])
  const [loading, setLoading] = useState(false)

  const fetchSubtask = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const data = await getStorageSubTask(id)
      setSubtask(data)
    } finally {
      setLoading(false)
    }
  }, [id])

  const fetchLogs = useCallback(async () => {
    if (!id) return
    try {
      const data = await getStorageSubTaskLogs(id)
      setLogs(data)
    } catch {
      // error handled by request interceptor
    }
  }, [id])

  useEffect(() => {
    setSubtask(null)
    setLogs([])
  }, [id])

  useEffect(() => {
    void fetchSubtask()
  }, [fetchSubtask])

  useEffect(() => {
    void fetchLogs()
  }, [fetchLogs])

  useEffect(() => {
    if (!id) return
    connectRealtime()

    const unsubscribeSubtask = subscribeRealtime<StorageSubTask>(
      'storage.sub.updated',
      (event: RealtimeEvent<StorageSubTask>) => {
        if (event.payload.id !== id) return
        setSubtask((current) => (current ? { ...current, ...event.payload } : event.payload))
      },
    )

    const unsubscribeLog = subscribeRealtime<StorageTaskLog>(
      'storage.sub.log.appended',
      (event: RealtimeEvent<StorageTaskLog>) => {
        if (event.resource_id !== id) return
        setLogs((current) => current.concat(event.payload))
      },
    )

    const unsubscribeResync = subscribeRealtime(
      'system.resync_required',
      () => {
        void fetchSubtask()
        void fetchLogs()
      },
    )

    return () => {
      unsubscribeSubtask()
      unsubscribeLog()
      unsubscribeResync()
    }
  }, [id, fetchSubtask, fetchLogs])

  return (
    <div className={styles.page}>
      {subtask && (
        <>
          <Card title="基本信息" style={{ marginBottom: 16 }} loading={loading}>
            <Descriptions column={2}>
              <Descriptions.Item label="番号">{subtask.movie_code}</Descriptions.Item>
              <Descriptions.Item label="标题">{subtask.movie_title || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusLabels[subtask.status]?.color}>
                  {statusLabels[subtask.status]?.text || subtask.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="步骤">{subtask.step || '-'}</Descriptions.Item>
              <Descriptions.Item label="存储模式">{subtask.storage_mode || '-'}</Descriptions.Item>
              <Descriptions.Item label="选择的存储位置">
                {subtask.selected_storage_location || '-'}
              </Descriptions.Item>
              {subtask.skip_reason && (
                <Descriptions.Item label="跳过原因" span={2}>
                  {subtask.skip_reason}
                </Descriptions.Item>
              )}
              {subtask.error_message && (
                <Descriptions.Item label="错误信息" span={2}>
                  <Typography.Text type="danger">{subtask.error_message}</Typography.Text>
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>

          <Card title="目标位置" style={{ marginBottom: 16 }}>
            {subtask.target_locations.length > 0 ? (
              <Descriptions column={1}>
                {subtask.target_locations.map((loc, index) => (
                  <Descriptions.Item key={loc} label={`位置 ${index + 1}`}>
                    {loc}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无目标位置" />
            )}
          </Card>

          <Card title="移动的文件" style={{ marginBottom: 16 }}>
            {subtask.moved_files.length > 0 ? (
              <Descriptions column={1}>
                {subtask.moved_files.map((file, index) => (
                  <Descriptions.Item key={index} label={`文件 ${index + 1}`}>
                    {JSON.stringify(file)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无移动文件" />
            )}
          </Card>

          <Card title="跳过的文件" style={{ marginBottom: 16 }}>
            {subtask.skipped_files.length > 0 ? (
              <Descriptions column={1}>
                {subtask.skipped_files.map((file, index) => (
                  <Descriptions.Item key={index} label={`文件 ${index + 1}`}>
                    {JSON.stringify(file)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无跳过文件" />
            )}
          </Card>

          <Card title="步骤时间线" style={{ marginBottom: 16 }}>
            <Timeline
              items={stepOrder.map((step) => {
                const stepLogs = logsForStep(logs, step)
                const lastLog = stepLogs.at(-1)
                return {
                  color: stepColor(subtask, stepLogs, step),
                  children: (
                    <div className={styles.stepTimelineItem}>
                      <div className={styles.stepTimelineHeader}>
                        <Typography.Text strong>{stepLabels[step]}</Typography.Text>
                        <Typography.Text type="secondary">{step}</Typography.Text>
                      </div>
                      {lastLog ? (
                        <Typography.Text
                          type={lastLog.level === 'ERROR' ? 'danger' : 'secondary'}
                          className={styles.stepTimelineMessage}
                        >
                          {formatTime(lastLog.timestamp)} {lastLog.message}
                        </Typography.Text>
                      ) : (
                        <Typography.Text type="secondary" className={styles.stepTimelineMessage}>
                          等待执行
                        </Typography.Text>
                      )}
                    </div>
                  ),
                }
              })}
            />
          </Card>

          <Card title="任务日志">
            {logs.length > 0 ? (
              <div style={{ maxHeight: 500, overflow: 'auto' }}>
                <Timeline
                  items={logs.map((log) => ({
                    color: levelColors[log.level] || 'default',
                    children: (
                      <div>
                        <Typography.Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
                          {formatTime(log.timestamp)}
                        </Typography.Text>
                        <Tag color={levelColors[log.level] || 'default'}>{log.level}</Tag>
                        <Typography.Text
                          type={log.level === 'ERROR' ? 'danger' : undefined}
                          style={{ wordBreak: 'break-word' }}
                        >
                          {log.message}
                        </Typography.Text>
                      </div>
                    ),
                  }))}
                />
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无日志" />
            )}
          </Card>
        </>
      )}

      {!subtask && !loading && (
        <Card>
          <Empty description="未找到子任务" />
        </Card>
      )}
    </div>
  )
}

export default StorageSubTaskDetailPage
