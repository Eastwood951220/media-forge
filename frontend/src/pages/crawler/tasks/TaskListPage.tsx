import { useCallback, useState } from 'react'
import { App, Modal, Select } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  batchCreateCrawlTasks,
  batchRunCrawlTasks,
  createTemporaryCrawlRun,
  getCrawlTaskTags,
  getTaskDict,
} from '@/api/crawler/crawlTask'
import type {
  BatchCrawlTaskRunAcceptedItem,
  TaskDictItem,
  TemporaryCrawlRunCreateParams,
} from '@/api/crawler/crawlTask/types'
import { queryKeys } from '@/api/queryKeys'
import { invalidateCrawlerRunLists, invalidateCrawlerTaskLists } from '@/api/queryInvalidation'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import type { CrawlTask } from '@/api/crawler/crawlTask/types'
import BatchTaskCreateDrawer from './components/BatchTaskCreateDrawer'
import type { BatchTaskCreateFormValues } from './components/BatchTaskCreateDrawer'
import TaskUrlRunModal from './components/TaskUrlRunModal'
import TemporaryTaskModal from './components/TemporaryTaskModal'
import { useTaskListData } from './hooks/useTaskListData'
import { useTaskListRealtime } from './hooks/useTaskListRealtime'
import { useTaskUrlRun } from './hooks/useTaskUrlRun'
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { MetricGrid } from '@/components/common'
import styles from './TaskPages.module.less'

function TaskListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { message } = App.useApp()

  const [selectedTagNames, setSelectedTagNames] = useState<string[]>([])
  const tagOptionsQuery = useQuery({
    queryKey: queryKeys.crawlerTasks.tags(),
    queryFn: getCrawlTaskTags,
  })

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
  } = useTaskListData({ tagNames: selectedTagNames })

  useTaskListRealtime()
  useRouteActivationRefresh(refreshList)

  const taskUrlRun = useTaskUrlRun({ onSubmitted: handleRunSubmitted })

  const [temporaryModalOpen, setTemporaryModalOpen] = useState(false)
  const [taskOptions, setTaskOptions] = useState<TaskDictItem[]>([])
  const [taskOptionsLoading, setTaskOptionsLoading] = useState(false)
  const [taskOptionsError, setTaskOptionsError] = useState<string | null>(null)
  const [temporarySubmitting, setTemporarySubmitting] = useState(false)

  const [batchDrawerOpen, setBatchDrawerOpen] = useState(false)
  const [batchSubmitting, setBatchSubmitting] = useState(false)
  const [batchFailedUrls, setBatchFailedUrls] = useState<string[]>([])
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])
  const [batchRunSubmitting, setBatchRunSubmitting] = useState(false)

  const markBatchRunsQueued = useCallback((accepted: BatchCrawlTaskRunAcceptedItem[]) => {
    const now = new Date().toISOString()
    for (const item of accepted) {
      useCrawlerRuntimeStore.getState().upsertTaskRuntime({
        task_id: item.task_id,
        runtime_status: 'queued',
        latest_run_id: item.run_id,
        state_updated_at: now,
        last_run_at: now,
      })
    }
  }, [])

  const openBatchRunConfirm = useCallback(() => {
    let crawlMode: 'incremental' | 'full' = 'incremental'
    Modal.confirm({
      title: '批量爬取',
      content: (
        <Select<'incremental' | 'full'>
          aria-label="爬取模式"
          defaultValue="incremental"
          options={[
            { value: 'incremental', label: '增量爬取' },
            { value: 'full', label: '全量爬取' },
          ]}
          onChange={(value) => {
            crawlMode = value
          }}
          style={{ width: '100%' }}
        />
      ),
      okText: '开始',
      cancelText: '取消',
      onOk: async () => {
        setBatchRunSubmitting(true)
        try {
          const result = await batchRunCrawlTasks({ task_ids: selectedTaskIds, crawl_mode: crawlMode })
          markBatchRunsQueued(result.accepted)
          await invalidateCrawlerRunLists(queryClient)
          setSelectedTaskIds([])
          if (result.failed_count > 0) {
            await message.warning(`已提交 ${result.accepted_count} 个任务，${result.failed_count} 个失败`)
          } else {
            await message.success(`已提交 ${result.accepted_count} 个任务`)
          }
        } catch (error) {
          await message.error(error instanceof Error ? error.message : '批量爬取失败')
        } finally {
          setBatchRunSubmitting(false)
        }
      },
    })
  }, [markBatchRunsQueued, message, queryClient, selectedTaskIds])

  const handleTagFilterChange = useCallback((nextTags: string[]) => {
    setSelectedTagNames(nextTags)
    setSelectedTaskIds([])
    setCurrent(1)
  }, [setCurrent])

  const handlePageChange = useCallback((page: number) => {
    setSelectedTaskIds([])
    setCurrent(page)
  }, [setCurrent])

  const handlePageSizeChange = useCallback((size: number) => {
    setSelectedTaskIds([])
    setPageSize(size)
  }, [setPageSize])

  const handleBatchSubmit = useCallback(async (values: BatchTaskCreateFormValues) => {
    setBatchSubmitting(true)
    try {
      const result = await batchCreateCrawlTasks(values)
      await invalidateCrawlerTaskLists(queryClient)
      if (result.failed_count > 0) {
        setBatchFailedUrls(result.failed.map((item) => item.url))
        await message.warning(`已创建 ${result.created_count} 个任务，${result.failed_count} 个失败`)
        return
      }
      setBatchFailedUrls([])
      setBatchDrawerOpen(false)
      await message.success(`已创建 ${result.created_count} 个任务`)
    } catch (error) {
      await message.error(error instanceof Error ? error.message : '批量新建任务失败')
    } finally {
      setBatchSubmitting(false)
    }
  }, [message, queryClient])

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
      await message.success('临时任务已提交')
      setTemporaryModalOpen(false)
      handleRunSubmitted()
    } catch (error) {
      await message.error(error instanceof Error ? error.message : '临时任务提交失败')
    } finally {
      setTemporarySubmitting(false)
    }
  }, [handleRunSubmitted, message])

  const taskStats = useCrawlerRuntimeStore((state) => state.taskStats)

  return (
    <div className={styles.page}>
      <section aria-label="任务统计">
        <MetricGrid
          items={[
            { key: 'total', label: '总数', value: taskStats?.total ?? 0, tone: 'default' },
            { key: 'idle', label: '空闲中', value: taskStats?.idle ?? 0, tone: 'success' },
            { key: 'running', label: '运行中', value: taskStats?.running ?? 0, tone: 'info' },
            { key: 'queued', label: '排队中', value: taskStats?.queued ?? 0, tone: 'warning' },
            { key: 'stopped', label: '停止中', value: taskStats?.stopped ?? 0, tone: 'danger' },
          ]}
        />
      </section>

      <section className={styles.panel}>
        <TaskListCards
          tasks={tasks as CrawlTask[]}
          loading={loading}
          total={total}
          runtimeByTaskId={runtimeByTaskId}
          runtimeReady={taskSnapshotReady}
          tagOptions={tagOptionsQuery.data ?? []}
          selectedTagNames={selectedTagNames}
          onTagFilterChange={handleTagFilterChange}
          selectedTaskIds={selectedTaskIds}
          onSelectedTaskIdsChange={setSelectedTaskIds}
          onBatchRunClick={openBatchRunConfirm}
          batchRunLoading={batchRunSubmitting}
          onEdit={(task) => navigate({ to: '/crawler/tasks/$id/edit', params: { id: task.id } })}
          onDelete={handleDelete}
          onToggleSkip={handleToggleSkip}
          onRun={handleRun}
          onStop={handleStop}
          onRestart={handleRestart}
          onUrlRun={taskUrlRun.openTaskUrlRun}
          onTemporaryTaskClick={openTemporaryModal}
          onBatchTaskClick={() => setBatchDrawerOpen(true)}
          current={current}
          pageSize={pageSize}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
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

      <BatchTaskCreateDrawer
        open={batchDrawerOpen}
        submitting={batchSubmitting}
        failedUrls={batchFailedUrls}
        tagOptions={tagOptionsQuery.data ?? []}
        tagOptionsLoading={tagOptionsQuery.isLoading}
        onCancel={() => {
          if (batchSubmitting) return
          setBatchDrawerOpen(false)
          setBatchFailedUrls([])
        }}
        onSubmit={handleBatchSubmit}
      />
    </div>
  )
}

export default TaskListPage
