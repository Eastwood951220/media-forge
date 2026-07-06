import { useParams } from '@tanstack/react-router'
import { Card, Empty, Tag, Timeline, Typography } from 'antd'
import { useStorageSubTaskDetail } from './hooks/useStorageSubTaskDetail'
import { useStorageSubTaskRealtime } from './hooks/useStorageSubTaskRealtime'
import { SubtaskInfoCard } from './components/SubtaskInfoCard'
import { SubtaskFilesCard } from './components/SubtaskFilesCard'
import {
  levelColors,
  stepOrder,
  stepLabels,
  logsForStep,
  stepColor,
  formatTime,
} from './utils/subtaskStatus'
import styles from './StorageTasks.module.less'

function StorageSubTaskDetailPage() {
  const { id } = useParams({ strict: false })
  const { subtask, setSubtask, logs, setLogs, loading, fetchSubtask, fetchLogs } =
    useStorageSubTaskDetail(id)

  useStorageSubTaskRealtime({
    id,
    setSubtask,
    setLogs,
    fetchSubtask,
    fetchLogs,
  })

  return (
    <div className={styles.page}>
      {subtask && (
        <>
          <SubtaskInfoCard subtask={subtask} loading={loading} />

          <SubtaskFilesCard subtask={subtask} />

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
