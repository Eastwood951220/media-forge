import {useCallback, useEffect, useState} from 'react'
import {useNavigate} from '@tanstack/react-router'
import {Modal, Select, Typography, message} from 'antd'
import {
    deleteCrawlTask,
    getCrawlTaskRuntimeStatuses,
    getCrawlTasks,
    updateCrawlTask,
} from '@/api/crawlTask'
import type {
    CrawlTask,
    CrawlTaskRuntimeSnapshot,
    CrawlTaskRuntimeStats,
    DeleteMode,
} from '@/api/crawlTask/types'
import {restartCrawlerRun, runCrawlTask, stopCrawlerRun} from '@/api/crawlerRun'
import type {CrawlMode} from '@/api/crawlerRun/types'
import {connectRealtime, subscribeRealtime} from '@/realtime/eventSourceClient'
import type {CrawlerTaskStatusUpdatedPayload} from '@/realtime/types'
import TaskListCards from '@/pages/crawler/tasks/components/TaskListCards'
import styles from './TaskPages.module.less'

const initialStats: CrawlTaskRuntimeStats = {
    total: 0,
    idle: 0,
    running: 0,
    queued: 0,
    stopped: 0,
}

const deleteModeOptions: Array<{ value: DeleteMode; label: string }> = [
    {value: 'task_only', label: '仅删除任务'},
    {value: 'task_and_movies', label: '删除任务和关联影片'},
    {value: 'task_movies_and_cloud', label: '删除任务、关联影片和云存储'},
]

function recomputeStats(runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>): CrawlTaskRuntimeStats {
    const rows = Object.values(runtimeByTaskId)
    return rows.reduce<CrawlTaskRuntimeStats>(
        (acc, row) => {
            acc.total += 1
            acc[row.runtime_status] += 1
            return acc
        },
        {total: 0, idle: 0, running: 0, queued: 0, stopped: 0},
    )
}

function TaskListPage() {
    const navigate = useNavigate()
    const [tasks, setTasks] = useState<CrawlTask[]>([])
    const [stats, setStats] = useState<CrawlTaskRuntimeStats>(initialStats)
    const [loading, setLoading] = useState(false)
    const [total, setTotal] = useState(0)
    const [runtimeByTaskId, setRuntimeByTaskId] = useState<Record<string, CrawlTaskRuntimeSnapshot>>({})

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

    const fetchRuntimeStatuses = useCallback(async () => {
        const data = await getCrawlTaskRuntimeStatuses()
        setRuntimeByTaskId(Object.fromEntries(data.tasks.map((item) => [item.task_id, item])))
        setStats(data.stats)
    }, [])

    const refreshList = useCallback(() => {
        void fetchTasks()
        void fetchRuntimeStatuses()
    }, [fetchRuntimeStatuses, fetchTasks])

    useEffect(() => {
        refreshList()
    }, [refreshList])

    // Subscribe to realtime task status updates
    useEffect(() => {
        connectRealtime()

        const unsubscribeTaskStatus = subscribeRealtime<CrawlerTaskStatusUpdatedPayload>(
            'crawler.task.status.updated',
            (event) => {
                const payload = event.payload
                setRuntimeByTaskId((current) => {
                    const next = {...current, [payload.task_id]: payload}
                    setStats(recomputeStats(next))
                    return next
                })
            },
        )

        const unsubscribeResync = subscribeRealtime(
            'system.resync_required',
            () => {
                refreshList()
            },
        )

        return () => {
            unsubscribeTaskStatus()
            unsubscribeResync()
        }
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
                                style={{width: '100%'}}
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
            await updateCrawlTask(task.id, {is_skip: !task.is_skip})
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
                void fetchRuntimeStatuses()
            } catch {
                message.error('启动爬取任务失败')
            }
        },
        [fetchRuntimeStatuses],
    )

    const handleStop = useCallback(
        async (task: CrawlTask) => {
            const runtime = runtimeByTaskId[task.id]
            if (!runtime?.latest_run_id) return
            try {
                await stopCrawlerRun(runtime.latest_run_id)
                message.success('已停止运行')
                refreshList()
            } catch (error) {
                const msg = error instanceof Error ? error.message : '停止失败'
                message.error(msg)
                void fetchRuntimeStatuses()
            }
        },
        [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
    )

    const handleRestart = useCallback(
        async (task: CrawlTask) => {
            const runtime = runtimeByTaskId[task.id]
            if (!runtime?.latest_run_id) return
            try {
                await restartCrawlerRun(runtime.latest_run_id)
                message.success('已重启运行')
                refreshList()
            } catch (error) {
                const msg = error instanceof Error ? error.message : '重启失败'
                message.error(msg)
                void fetchRuntimeStatuses()
            }
        },
        [fetchRuntimeStatuses, refreshList, runtimeByTaskId],
    )

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
