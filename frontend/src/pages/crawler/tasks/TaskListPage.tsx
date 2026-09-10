import { useCallback, useState } from 'react'
import { App, Input, Modal, Select } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import {
  batchCreateCrawlTasks,
  batchRunCrawlTasks,
  createTemporaryCrawlRun,
  getTaskDict,
} from '@/api/crawler/crawlTask'
import type {
  BatchCrawlTaskRunAcceptedItem,
  TaskDictItem,
  TemporaryCrawlRunCreateParams,
} from '@/api/crawler/crawlTask/types'
import { queryKeys } from '@/api/queryKeys'
import { invalidateCrawlerRunLists, invalidateCrawlerTaskLists } from '@/api/queryInvalidation'
import { fetchActressesFromTask } from '@/api/content/actresses'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import type { CrawlTask, TaskUrlEntry } from '@/api/crawler/crawlTask/types'
import BatchTaskCreateDrawer from './components/BatchTaskCreateDrawer'
import type { BatchTaskCreateFormValues } from './components/BatchTaskCreateDrawer'
import TaskUrlRunModal from './components/TaskUrlRunModal'
import TemporaryTaskModal from './components/TemporaryTaskModal'
import { useTaskListData } from './hooks/useTaskListData'
import { useTaskListRealtime } from './hooks/useTaskListRealtime'
import { useTaskUrlRun } from './hooks/useTaskUrlRun'
import { useRouteActivationRefresh } from '@/hooks/useRouteActivationRefresh'
import { useCrawlerRuntimeStore } from '@/stores/useCrawlerRuntimeStore'
import { useTaskListQueryStore } from './useTaskListQueryStore'
import { MetricGrid } from '@/components/common'
import styles from './TaskPages.module.less'

type ActorTaskUrl = TaskUrlEntry & { id: string }

function getActorUrls(task: CrawlTask): ActorTaskUrl[] {
  return task.urls.filter((url): url is ActorTaskUrl => url.url_type === 'actors' && Boolean(url.id))
}

function formatActorUrlOption(url: ActorTaskUrl, index: number) {
  const name = url.url_name?.trim()
  return name ? `${name} - ${url.url}` : `演员 URL ${index + 1} - ${url.url}`
}

function TaskListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
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

  const [batchDrawerOpen, setBatchDrawerOpen] = useState(false)
  const [batchSubmitting, setBatchSubmitting] = useState(false)
  const [batchFailedUrls, setBatchFailedUrls] = useState<string[]>([])
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([])
  const [batchRunSubmitting, setBatchRunSubmitting] = useState(false)
  const [fetchingActressTaskId, setFetchingActressTaskId] = useState<string | null>(null)
  const [actressPickerTask, setActressPickerTask] = useState<CrawlTask | null>(null)
  const [selectedActressTaskUrlId, setSelectedActressTaskUrlId] = useState<string | undefined>()

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

  const keyword = useTaskListQueryStore((state) => state.keyword)
  const setKeyword = useTaskListQueryStore((state) => state.setKeyword)

  const handleKeywordChange = useCallback((nextKeyword: string) => {
    // Page-1 reset happens in useTaskListData when the keyword changes.
    setKeyword(nextKeyword)
    setSelectedTaskIds([])
  }, [setKeyword])

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

  const submitActressFetch = useCallback(async (task: CrawlTask, taskUrlId: string, avjohoUrl?: string) => {
    setFetchingActressTaskId(task.id)
    try {
      const result = await fetchActressesFromTask({
        task_id: task.id,
        task_url_id: taskUrlId,
        avjoho_url: avjohoUrl || undefined,
      })
      await queryClient.invalidateQueries({ queryKey: queryKeys.actresses.all() })
      if (result.matched) {
        await message.success(`已获取 ${result.profiles.length} 位女优资料`)
        return
      }
      if (avjohoUrl) {
        await message.warning(result.message || '未匹配到 avjoho 资料')
        return
      }
      let manualUrl = ''
      Modal.confirm({
        title: '填写 avjoho 资料页',
        content: (
          <Input
            aria-label="avjoho 资料页 URL"
            placeholder="https://db.avjoho.com/..."
            onChange={(event) => {
              manualUrl = event.target.value
            }}
          />
        ),
        okText: '获取',
        cancelText: '取消',
        onOk: async () => {
          if (!manualUrl.trim()) {
            await message.warning('请填写 avjoho URL')
            throw new Error('avjoho_url_required')
          }
          await submitActressFetch(task, taskUrlId, manualUrl.trim())
        },
      })
    } catch (error) {
      await message.error(error instanceof Error ? error.message : '获取女优资料失败')
    } finally {
      setFetchingActressTaskId(null)
    }
  }, [message, queryClient])

  const handleFetchActresses = useCallback((task: CrawlTask) => {
    const actorUrls = getActorUrls(task)
    if (actorUrls.length === 0) {
      void message.warning('当前任务没有可获取资料的演员 URL')
      return
    }
    if (actorUrls.length === 1 && actorUrls[0].id) {
      void submitActressFetch(task, actorUrls[0].id)
      return
    }
    setActressPickerTask(task)
    setSelectedActressTaskUrlId(undefined)
  }, [message, submitActressFetch])

  const selectedActorUrls = actressPickerTask ? getActorUrls(actressPickerTask) : []

  const handleActressPickerCancel = useCallback(() => {
    setActressPickerTask(null)
    setSelectedActressTaskUrlId(undefined)
  }, [])

  const handleActressPickerOk = useCallback(() => {
    if (!actressPickerTask || !selectedActressTaskUrlId) return
    const task = actressPickerTask
    const taskUrlId = selectedActressTaskUrlId
    handleActressPickerCancel()
    void submitActressFetch(task, taskUrlId)
  }, [actressPickerTask, handleActressPickerCancel, selectedActressTaskUrlId, submitActressFetch])

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
          keyword={keyword}
          onKeywordChange={handleKeywordChange}
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
          onViewMovies={(task) => navigate({ to: '/content/movies', search: { task_id: task.id } })}
          onFetchActresses={handleFetchActresses}
          fetchingActressTaskId={fetchingActressTaskId}
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

      <Modal
        title="选择演员 URL"
        open={Boolean(actressPickerTask)}
        okText="获取"
        cancelText="取消"
        okButtonProps={{ disabled: !selectedActressTaskUrlId }}
        onOk={handleActressPickerOk}
        onCancel={handleActressPickerCancel}
      >
        <Select
          aria-label="演员 URL"
          placeholder="请选择演员 URL"
          value={selectedActressTaskUrlId}
          options={selectedActorUrls.map((url, index) => ({
            value: url.id,
            label: formatActorUrlOption(url, index),
          }))}
          onChange={setSelectedActressTaskUrlId}
          style={{ width: '100%' }}
        />
      </Modal>

      <BatchTaskCreateDrawer
        open={batchDrawerOpen}
        submitting={batchSubmitting}
        failedUrls={batchFailedUrls}
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
