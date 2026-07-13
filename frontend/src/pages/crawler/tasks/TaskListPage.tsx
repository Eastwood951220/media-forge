import { useCallback, useState } from 'react'
import { App } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { createTemporaryCrawlRun, getTaskDict } from '@/api/crawlTask'
import type { TaskDictItem, TemporaryCrawlRunCreateParams } from '@/api/crawlTask/types'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import TemporaryTaskModal from './components/TemporaryTaskModal'
import { useTaskListData } from './hooks/useTaskListData'
import { useTaskListRealtime } from './hooks/useTaskListRealtime'
import styles from './TaskPages.module.less'

function TaskListPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()

  const {
    fetchRuntimeStatuses,
    handleDelete,
    handleRestart,
    handleRun,
    handleStop,
    handleToggleSkip,
    loading,
    refreshList,
    runtimeByTaskId,
    setRuntimeByTaskId,
    setStats,
    stats,
    tasks,
    total,
  } = useTaskListData()

  useTaskListRealtime({ refreshList, setRuntimeByTaskId, setStats })

  const [temporaryModalOpen, setTemporaryModalOpen] = useState(false)
  const [taskOptions, setTaskOptions] = useState<TaskDictItem[]>([])
  const [taskOptionsLoading, setTaskOptionsLoading] = useState(false)
  const [taskOptionsError, setTaskOptionsError] = useState<string | null>(null)
  const [temporarySubmitting, setTemporarySubmitting] = useState(false)

  const loadTaskOptions = useCallback(async () => {
    setTaskOptionsLoading(true)
    setTaskOptionsError(null)
    try {
      setTaskOptions(await getTaskDict())
    } catch (error) {
      setTaskOptionsError(error instanceof Error ? error.message : '任务列表加载失败')
    } finally {
      setTaskOptionsLoading(false)
    }
  }, [])

  const openTemporaryModal = useCallback(() => {
    setTemporaryModalOpen(true)
    void loadTaskOptions()
  }, [loadTaskOptions])

  const handleTemporarySubmit = useCallback(async (payload: TemporaryCrawlRunCreateParams) => {
    setTemporarySubmitting(true)
    try {
      await createTemporaryCrawlRun(payload)
      message.success('临时任务已提交')
      setTemporaryModalOpen(false)
      void fetchRuntimeStatuses()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '临时任务提交失败')
    } finally {
      setTemporarySubmitting(false)
    }
  }, [fetchRuntimeStatuses, message])

  return (
    <div className={styles.page}>
      <section className={styles.statsBar} aria-label="任务统计">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>总数</span>
          <span className={styles.statValue}>{stats.total}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>空闲中</span>
          <span className={styles.statValue}>{stats.idle}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>运行中</span>
          <span className={styles.statValue}>{stats.running}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>排队中</span>
          <span className={styles.statValue}>{stats.queued}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>停止中</span>
          <span className={styles.statValue}>{stats.stopped}</span>
        </div>
      </section>

      <section className={styles.panel}>
        <TaskListCards
          tasks={tasks}
          loading={loading}
          total={total}
          runtimeByTaskId={runtimeByTaskId}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onRun={handleRun}
          onStop={handleStop}
          onRestart={handleRestart}
          onTemporaryTaskClick={openTemporaryModal}
        />
      </section>

      <TemporaryTaskModal
        open={temporaryModalOpen}
        tasks={taskOptions}
        tasksLoading={taskOptionsLoading}
        tasksError={taskOptionsError}
        submitting={temporarySubmitting}
        onCancel={() => setTemporaryModalOpen(false)}
        onReloadTasks={loadTaskOptions}
        onSubmit={handleTemporarySubmit}
      />
    </div>
  )
}

export default TaskListPage
