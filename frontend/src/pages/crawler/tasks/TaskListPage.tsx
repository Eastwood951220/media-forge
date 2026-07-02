import { useCallback, useEffect, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { Button, Modal, message } from 'antd'
import {
  deleteCrawlTask,
  getCrawlTasks,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTask } from '@/api/crawlTask/types'
import { runCrawlTask } from '@/api/crawlerRun'
import type { CrawlMode } from '@/api/crawlerRun/types'
import TaskListTable from '@/pages/crawler/tasks/components/TaskListTable.tsx'
import { useTaskListQueryStore } from './useTaskListQueryStore'
import styles from './TaskPages.module.less'

const PAGE_SIZE = 20

function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<CrawlTask[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)

  const keyword = useTaskListQueryStore((state) => state.keyword)
  const current = useTaskListQueryStore((state) => state.current)
  const setKeyword = useTaskListQueryStore((state) => state.setKeyword)
  const setCurrent = useTaskListQueryStore((state) => state.setCurrent)

  const fetchTasks = useCallback(async (page: number, nextKeyword: string) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const normalizedKeyword = nextKeyword.trim()
      const data = await getCrawlTasks({
        skip,
        limit: PAGE_SIZE,
        keyword: normalizedKeyword || undefined,
      })
      setTasks(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchTasks(current, keyword)
  }, [current, fetchTasks, keyword])

  const handlePageChange = useCallback(
    (page: number) => {
      setCurrent(page)
    },
    [setCurrent],
  )

  const handleDelete = useCallback(
    (task: CrawlTask) => {
      Modal.confirm({
        title: '确认删除',
        content: `确定删除任务「${task.name}」？此操作不可撤销。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: async () => {
          await deleteCrawlTask(task.id)
          message.success('删除成功')
          void fetchTasks(current, keyword)
        },
      })
    },
    [current, fetchTasks, keyword],
  )

  const handleSearch = useCallback(
    (nextKeyword: string) => {
      setKeyword(nextKeyword)
    },
    [setKeyword],
  )

  const handleToggleSkip = useCallback(
    async (task: CrawlTask) => {
      await updateCrawlTask(task.id, { is_skip: !task.is_skip })
      message.success(task.is_skip ? '任务已启用' : '任务已禁用')
      void fetchTasks(current, keyword)
    },
    [current, fetchTasks, keyword],
  )

  const handleRun = useCallback(
    async (task: CrawlTask, mode: CrawlMode) => {
      try {
        await runCrawlTask(task.id, mode)
        message.success(`已提交${mode === 'incremental' ? '增量' : '全量'}爬取任务`)
        navigate({ to: '/crawler/runs' })
      } catch (error) {
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

      <section className={styles.panel}>
        <TaskListTable
          tasks={tasks}
          loading={loading}
          total={total}
          current={current}
          pageSize={PAGE_SIZE}
          keyword={keyword}
          onKeywordChange={setKeyword}
          onPageChange={handlePageChange}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onSearch={handleSearch}
          onRun={handleRun}
        />
      </section>
    </div>
  )
}

export default TaskListPage
