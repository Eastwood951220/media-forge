import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined, PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Empty, Popover, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { CrawlTask, CrawlTaskRuntimeSnapshot, TaskRuntimeStatus } from '@/api/crawlTask/types'
import type { CrawlMode } from '@/api/crawlerRun/types'
import styles from '../TaskPages.module.less'
import {useNavigate} from "@tanstack/react-router";

type TaskListCardsProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
  onStop: (task: CrawlTask) => void
  onRestart: (task: CrawlTask) => void
  onUrlRun: (task: CrawlTask) => void
  onTemporaryTaskClick: () => void
}

const runtimeStatusLabels: Record<TaskRuntimeStatus, { text: string; color: string }> = {
  idle: { text: '空闲中', color: 'success' },
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  stopped: { text: '停止中', color: 'warning' },
}

function runtimeStatusTag(runtime?: CrawlTaskRuntimeSnapshot) {
  const status = runtime?.runtime_status ?? 'idle'
  const statusConfig = runtimeStatusLabels[status]
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function formatDateTime(value: string | null) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function getUrlNames(task: CrawlTask) {
  return task.urls
    .map((url) => url.url_name?.trim())
    .filter((name): name is string => Boolean(name))
}

const MAX_VISIBLE_URL_NAMES = 3

function UrlNameTags({ urlNames }: { urlNames: string[] }) {
  if (urlNames.length === 0) {
    return <Typography.Text type="secondary">-</Typography.Text>
  }

  if (urlNames.length <= MAX_VISIBLE_URL_NAMES) {
    return (
      <div className={styles.urlNameList}>
        {urlNames.map((name, index) => (
          <Tag key={`${name}-${index}`}>{name}</Tag>
        ))}
      </div>
    )
  }

  const visibleNames = urlNames.slice(0, MAX_VISIBLE_URL_NAMES)
  const hiddenCount = urlNames.length - MAX_VISIBLE_URL_NAMES

  return (
    <div className={styles.urlNameList}>
      {visibleNames.map((name, index) => (
        <Tag key={`${name}-${index}`}>{name}</Tag>
      ))}
      <Popover
        content={
          <div className={styles.urlNamePopover}>
            {urlNames.map((name, index) => (
              <Tag key={`${name}-${index}`} className={styles.urlNamePopoverTag}>{name}</Tag>
            ))}
          </div>
        }
        title="全部 URL 名称"
        trigger="hover"
        placement="bottomLeft"
      >
        <Tag className={styles.urlNameMore}>+{hiddenCount}</Tag>
      </Popover>
    </div>
  )
}

function TaskCard({
  task,
  runtime,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
  onStop,
  onRestart,
  onUrlRun,
}: {
  task: CrawlTask
  runtime: CrawlTaskRuntimeSnapshot | undefined
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
  onStop: (task: CrawlTask) => void
  onRestart: (task: CrawlTask) => void
  onUrlRun: (task: CrawlTask) => void
}) {
  const urlNames = getUrlNames(task)
  const runtimeStatus = runtime?.runtime_status ?? 'idle'
  const isIdle = runtimeStatus === 'idle'
  const canRun = isIdle && !task.is_skip
  const hasUrls = task.urls.length > 0
  const canUrlRun = canRun && hasUrls
  const canEditOrDelete = isIdle
  const canToggle = isIdle
  const canStop = (runtimeStatus === 'queued' || runtimeStatus === 'running') && Boolean(runtime?.latest_run_id)
  const canRestart = runtimeStatus === 'stopped' && Boolean(runtime?.latest_run_id)

  const runItems: MenuProps['items'] = [
    { key: 'incremental', label: '增量爬取', icon: <PlayCircleOutlined /> },
    { key: 'full', label: '全量爬取', icon: <PlayCircleOutlined /> },
  ]

  return (
    <article className={task.is_skip ? `${styles.taskCard} ${styles.taskCardDisabled}` : styles.taskCard}>
      <div className={styles.taskCardHead}>
        <Tooltip title={task.name}>
          <Typography.Text strong className={styles.taskCardTitle}>
            {task.name}
          </Typography.Text>
        </Tooltip>
        {runtimeStatusTag(runtime)}
      </div>

      <div className={styles.taskCardBody}>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>网盘路径</span>
          <Typography.Text className={styles.taskMetaValue}>{task.storage_location || '-'}</Typography.Text>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>URL 名称</span>
          <UrlNameTags urlNames={urlNames} />
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>最后爬取时间</span>
          <Typography.Text className={styles.taskMetaValue}>{formatDateTime(runtime?.last_run_at ?? null)}</Typography.Text>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>状态</span>
          <Space size={8}>
            <Switch
              checked={!task.is_skip}
              onChange={() => onToggleSkip(task)}
              checkedChildren="启用"
              unCheckedChildren="禁用"
              size="small"
              disabled={!canToggle}
            />
          </Space>
        </div>
      </div>

      <div className={styles.taskCardFooter}>
        {canRun && (
          <Dropdown
            menu={{
              items: runItems,
              onClick: ({ key }) => onRun(task, key as CrawlMode),
            }}
            trigger={['click']}
          >
            <Button type="primary" size="small" icon={<PlayCircleOutlined />}>
              爬取
            </Button>
          </Dropdown>
        )}
        <Button
          size="small"
          icon={<PlayCircleOutlined />}
          disabled={!canUrlRun}
          onClick={() => onUrlRun(task)}
        >
          URL 爬取
        </Button>
        {canStop && (
          <Button size="small" danger icon={<StopOutlined />} onClick={() => onStop(task)}>
            停止
          </Button>
        )}
        {canRestart && (
          <Button size="small" type="primary" icon={<ReloadOutlined />} onClick={() => onRestart(task)}>
            重启
          </Button>
        )}
        {canEditOrDelete && (
          <Space size={4}>
            <Tooltip title="编辑">
              <Button
                aria-label={`编辑 ${task.name}`}
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => onEdit(task)}
              />
            </Tooltip>
            <Tooltip title="删除">
              <Button
                aria-label={`删除 ${task.name}`}
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => onDelete(task)}
              />
            </Tooltip>
          </Space>
        )}
      </div>
    </article>
  )
}

function TaskListCards({
  tasks,
  loading,
  total,
  runtimeByTaskId,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
  onStop,
  onRestart,
  onUrlRun,
  onTemporaryTaskClick,
}: TaskListCardsProps) {
  const navigate = useNavigate()
  return (
    <div className={styles.taskListShell}>
      <div className={styles.taskListToolbar}>
        <Typography.Text type="secondary">共 {total} 条</Typography.Text>
        <Space>
          <Button onClick={onTemporaryTaskClick}>
            临时任务
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate({ to: '/crawler/tasks/new' })}
          >
            新建任务
          </Button>
        </Space>
      </div>

      <Spin spinning={loading}>
        {tasks.length > 0 ? (
          <div className={styles.taskGrid}>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                runtime={runtimeByTaskId[task.id]}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleSkip={onToggleSkip}
                onRun={onRun}
                onStop={onStop}
                onRestart={onRestart}
                onUrlRun={onUrlRun}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无任务" className={styles.emptyState} />
        )}
      </Spin>
    </div>
  )
}

export default TaskListCards
