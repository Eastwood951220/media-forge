import type { StorageTaskLog } from '@/api/storage/storageTasks/types'
import { LogList } from '@/components/common'
import { formatTime } from '../utils/format'

const levelColors: Record<string, string> = {
  ERROR: 'red',
  WARNING: 'orange',
  INFO: 'blue',
  DEBUG: 'default',
}

export default function SubtaskLogList({ logs }: { logs: StorageTaskLog[] }) {
  return (
    <LogList
      items={logs.map((log, index) => ({
        id: `${log.timestamp}-${index}`,
        timestamp: log.timestamp,
        level: log.level.toUpperCase(),
        message: log.context ? `${log.message} ${JSON.stringify(log.context)}` : log.message,
      }))}
      levelColorMap={levelColors}
      formatTime={formatTime}
    />
  )
}
