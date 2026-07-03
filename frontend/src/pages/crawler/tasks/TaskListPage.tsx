import { useCallback, useEffect, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Modal, Select, Typography, message } from 'antd'
import {
  deleteCrawlTask,
  getCrawlTaskStats,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTask, CrawlTaskStats, DeleteMode } from '@/api/crawlTask/types'
import { runCrawlTask } from '@/api/crawlerRun'
import type { CrawlMode } from '@/api/crawlerRun/types'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import styles from './TaskPages.module.less'

const initialStats: CrawlTaskStats = {
  total: 0,
  enabled: 0,
  disabled: 0,
}

const deleteModeOptions: Array<{ value: DeleteMode; label: string }> = [
  { value: 'task_only', label: '仅删除任务' },
  { value: 'task_and_movies', label: '删除任务和关联影片' },
  { value: 'task_movies_and_cloud', label: '删除任务、关联影片和云存储' },
]

function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<CrawlTask[]>([])
  const [stats, setStats] = useState<CrawlTaskStats>(initialStats)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  const fetchStats = useCallback(async () => {
    const data = await getCrawlTaskStats()
    setStats(data)
  }, [])

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getCrawlTasks()
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshList = useCallback(() => {
    void fetchTasks()
    void fetchStats()
  }, [fetchStats, fetchTasks])

  useEffect(() => {
    refreshList()
  }, [refreshList])

  const handleDelete = useCallback(
    (task: CrawlTask) => {
      let selectedMode: DeleteMode = 'task_only'

      Modal.confirm({
        title: '确认删除',
        content: (
          <div>
            <p>确定删除任务「{task.name}」？</p>
            <div className={styles.deleteModeRow}>
              <Typography.Text className={styles.deleteModeLabel}>删除模式</Typography.Text>
              <Select<DeleteMode>
                aria-label="删除模式"
                defaultValue="task_only"
                options={deleteModeOptions}
                onChange={(value) => {
                  selectedMode = value
                }}
                style={{ width: '100%' }}
              />
            </div>
            <Typography.Text type="danger" className={styles.deleteWarning}>
              删除任务和关联影片将永久删除该任务独占的影片数据，且不可撤销。
            </Typography.Text>
          </div>
        ),
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        width: 500,
        onOk: async () => {
          const result = await deleteCrawlTask(task.id, selectedMode)
          const msg = selectedMode === 'task_and_movies'
            ? `，已删除 ${result?.deleted_movies ?? 0} 部关联影片`
            : ''
          message.success(`删除成功${msg}`)
          refreshList()
        },
      })
    },
    [refreshList],
  )

  const handleToggleSkip = useCallback(
    async (task: CrawlTask) => {
      await updateCrawlTask(task.id, { is_skip: !task.is_skip })
      message.success(task.is_skip ? '任务已启用' : '任务已禁用')
      refreshList()
    },
    [refreshList],
  )

  const handleRun = useCallback(
    async (task: CrawlTask, mode: CrawlMode) => {
      try {
        await runCrawlTask(task.id, mode)
        message.success(`已提交${mode === 'incremental' ? '增量' : '全量'}爬取任务`)
        void navigate({ to: '/crawler/runs' })
      } catch {
        message.error('启动爬取任务失败')
      }
    },
    [navigate],
  )

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>爬取任务</h1>
          <p className={styles.subtitle}>管理 JavDB 媒体资源的爬取任务</p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => navigate({ to: '/crawler/tasks/new' })}
        >
          新建任务
        </Button>
      </div>

      <section className={styles.statsBar} aria-label="任务统计">
        <div className={styles.statCard}>
          <span className={styles.statLabel}>总数</span>
          <span className={styles.statValue}>{stats.total}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>启用</span>
          <span className={styles.statValue}>{stats.enabled}</span>
        </div>
        <div className={styles.statCard}>
          <span className={styles.statLabel}>禁用</span>
          <span className={styles.statValue}>{stats.disabled}</span>
        </div>
      </section>

      <section className={styles.panel}>
        <TaskListCards
          tasks={tasks}
          loading={loading}
          total={total}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onRun={handleRun}
        />
      </section>
    </div>
  )
}

export default TaskListPage
