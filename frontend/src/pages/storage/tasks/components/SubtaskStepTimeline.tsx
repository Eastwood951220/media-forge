import { Timeline } from 'antd'
import type { StorageSubTask, StorageTaskLog } from '@/api/storage/storageTasks/types'
import { logsForStep, stepColor } from '../utils/format'

const stepOrder = ['prepare', 'submit', 'download', 'rename', 'move', 'verify'] as const
const stepLabels: Record<string, string> = {
  prepare: '准备',
  submit: '提交下载',
  download: '下载中',
  rename: '重命名',
  move: '移动',
  verify: '验证',
}

export default function SubtaskStepTimeline({
  subtask,
  logs,
}: {
  subtask: StorageSubTask
  logs: StorageTaskLog[]
}) {
  return (
    <Timeline
      items={stepOrder.map((step, index) => ({
        color: stepColor(subtask, logs, step),
        children: (
          <div key={index}>
            <strong>{stepLabels[step] ?? step}</strong>
            {logsForStep(logs, step).map((log, logIndex) => (
              <div key={logIndex} style={{ fontSize: 12, color: '#666' }}>
                {log.message}
              </div>
            ))}
          </div>
        ),
      }))}
    />
  )
}
