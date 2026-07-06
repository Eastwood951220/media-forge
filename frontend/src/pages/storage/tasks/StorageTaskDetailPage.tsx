import { useParams } from '@tanstack/react-router'
import { StorageMainSummaryCard } from './components/StorageMainSummaryCard'
import { StorageSubTaskTable } from './components/StorageSubTaskTable'
import { useStorageTaskDetail } from './hooks/useStorageTaskDetail'
import { useStorageTaskDetailRealtime } from './hooks/useStorageTaskDetailRealtime'
import styles from './StorageTasks.module.less'

function StorageTaskDetailPage() {
  const { id } = useParams({ strict: false })
  const detail = useStorageTaskDetail(id)

  useStorageTaskDetailRealtime({
    id,
    fetchSubtasks: detail.fetchSubtasks,
    fetchTask: detail.fetchTask,
    setSubtasks: detail.setSubtasks,
    setTask: detail.setTask,
  })

  return (
    <div className={styles.page}>
      <StorageMainSummaryCard
        actionLoading={detail.actionLoading}
        loading={detail.loading}
        onRestart={detail.handleRestart}
        onStop={detail.handleStop}
        task={detail.task}
      />
      <StorageSubTaskTable
        loading={detail.subtasksLoading}
        subtasks={detail.subtasks}
      />
    </div>
  )
}

export default StorageTaskDetailPage
