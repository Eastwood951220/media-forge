import { Tag } from 'antd'
import type { StorageTaskLog } from '@/api/storage/storageTasks/types'
import { formatTime } from '../utils/format'

const levelColors: Record<string, string> = {
  error: 'red',
  warning: 'orange',
  info: 'blue',
  debug: 'default',
}

export default function SubtaskLogList({ logs }: { logs: StorageTaskLog[] }) {
  return (
    <div>
      {logs.map((log, index) => (
        <div key={index} style={{ marginBottom: 8 }}>
          <Tag color={levelColors[log.level] ?? 'default'}>{log.level.toUpperCase()}</Tag>
          <span>{log.message}</span>
          {log.context && (
            <span style={{ color: '#999', marginLeft: 8 }}>
              {JSON.stringify(log.context)}
            </span>
          )}
          <span style={{ color: '#999', marginLeft: 8, fontSize: 12 }}>
            {formatTime(log.timestamp)}
          </span>
        </div>
      ))}
    </div>
  )
}
