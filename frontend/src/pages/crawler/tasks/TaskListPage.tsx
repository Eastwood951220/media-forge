import {useNavigate} from '@tanstack/react-router'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import {useTaskListData} from './hooks/useTaskListData'
import {useTaskListRealtime} from './hooks/useTaskListRealtime'
import styles from './TaskPages.module.less'

function TaskListPage() {
  const navigate = useNavigate()

  const {
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

  useTaskListRealtime({refreshList, setRuntimeByTaskId, setStats})

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
          onEdit={(task) => navigate({to: '/crawler/tasks/$id/edit', params: {id: task.id}})}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onRun={handleRun}
          onStop={handleStop}
          onRestart={handleRestart}
        />
      </section>
    </div>
  )
}

export default TaskListPage
