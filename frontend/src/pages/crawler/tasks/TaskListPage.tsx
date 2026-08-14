import { useCallback, useState } from 'react'
import { App } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { createTemporaryCrawlRun, getTaskDict } from '@/api/crawler/crawlTask'
import type { TaskDictItem, TemporaryCrawlRunCreateParams } from '@/api/crawler/crawlTask/types'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import type { CrawlTask } from '@/api/crawler/crawlTask/types'
import TaskUrlRunModal from './components/TaskUrlRunModal'
import TemporaryTaskModal from './components/TemporaryTaskModal'
import { useTaskListData } from './hooks/useTaskListData'
import { useTaskListRealtime } from './hooks/useTaskListRealtime'
import { useTaskUrlRun } from './hooks/useTaskUrlRun'
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import styles from './TaskPages.module.less'

function TaskListPage() {
  const navigate = useNavigate()
  const { message } = App.useApp()

  const {
    current,
    pageSize,
    total,
    setCurrent,
    setPageSize,
    handleDelete,
    handleRestart,
    handleRun,
    handleRunSubmitted,
    handleStop,
    handleToggleSkip,
    loading,
    refreshList,
    runtimeByTaskId,
    taskSnapshotReady,
    tasks,
  } = useTaskListData()

  useTaskListRealtime()
  useRouteActivationRefresh(refreshList)

  const taskUrlRun = useTaskUrlRun({ onSubmitted: handleRunSubmitted })

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
      handleRunSubmitted()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '临时任务提交失败')
    } finally {
      setTemporarySubmitting(false)
    }
  }, [handleRunSubmitted, message])

  const taskStats = useCrawlerRuntimeStore((state) => state.taskStats)

  return (
    <div className={styles.page}>
      <section className={styles.statsBar} aria-label="任务统计">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>总数</span>
          <span className={styles.statValue}>{taskStats?.total ?? 0}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>空闲中</span>
          <span className={styles.statValue}>{taskStats?.idle ?? 0}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>运行中</span>
          <span className={styles.statValue}>{taskStats?.running ?? 0}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>排队中</span>
          <span className={styles.statValue}>{taskStats?.queued ?? 0}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>停止中</span>
          <span className={styles.statValue}>{taskStats?.stopped ?? 0}</span>
        </div>
      </section>

      <section className={styles.panel}>
        <TaskListCards
          tasks={tasks as CrawlTask[]}
          loading={loading}
          total={total}
          runtimeByTaskId={runtimeByTaskId}
          runtimeReady={taskSnapshotReady}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onRun={handleRun}
          onStop={handleStop}
          onRestart={handleRestart}
          onUrlRun={taskUrlRun.openTaskUrlRun}
          onTemporaryTaskClick={openTemporaryModal}
          current={current}
          pageSize={pageSize}
          onPageChange={setCurrent}
          onPageSizeChange={setPageSize}
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

      <TaskUrlRunModal
        open={taskUrlRun.open}
        task={taskUrlRun.selectedTask}
        submitting={taskUrlRun.submitting}
        onCancel={taskUrlRun.closeTaskUrlRun}
        onSubmit={taskUrlRun.submitTaskUrlRun}
      />
    </div>
  )
}

export default TaskListPage
