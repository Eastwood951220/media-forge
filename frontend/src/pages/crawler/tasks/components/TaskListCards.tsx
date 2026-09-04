import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined, PlusOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Button, Checkbox, Dropdown, Empty, Pagination, Popover, Select, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { CrawlTask, CrawlTaskRuntimeSnapshot, TaskRuntimeStatus, TaskTag } from '@/api/crawler/crawlTask/types'
import type { CrawlMode } from '@/api/crawler/crawlerRun/types'
import styles from '../TaskPages.module.less'
import {useNavigate} from "@tanstack/react-router";

type TaskListCardsProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  runtimeByTaskId: Record<string, CrawlTaskRuntimeSnapshot>
  runtimeReady: boolean
  tagOptions: TaskTag[]
  selectedTagNames: string[]
  onTagFilterChange: (tagNames: string[]) => void
  selectedTaskIds: string[]
  onSelectedTaskIdsChange: (ids: string[]) => void
  onBatchRunClick: () => void
  batchRunLoading: boolean
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
  onStop: (task: CrawlTask) => void
  onRestart: (task: CrawlTask) => void
  onUrlRun: (task: CrawlTask) => void
  onTemporaryTaskClick: () => void
  onBatchTaskClick: () => void
  current: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
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

const MAX_VISIBLE_TAGS = 3

function TaskTagTags({ tags }: { tags: TaskTag[] }) {
  if (tags.length === 0) {
    return <Typography.Text type="secondary">-</Typography.Text>
  }

  if (tags.length <= MAX_VISIBLE_TAGS) {
    return (
      <div className={styles.urlNameList}>
        {tags.map((tag, index) => (
          <Tag key={`${tag.name}-${index}`}>{tag.name}</Tag>
        ))}
      </div>
    )
  }

  const visibleTags = tags.slice(0, MAX_VISIBLE_TAGS)
  const hiddenCount = tags.length - MAX_VISIBLE_TAGS

  return (
    <div className={styles.urlNameList}>
      {visibleTags.map((tag, index) => (
        <Tag key={`${tag.name}-${index}`}>{tag.name}</Tag>
      ))}
      <Popover
        content={
          <div className={styles.urlNamePopover}>
            {tags.map((tag, index) => (
              <Tag key={`${tag.name}-${index}`} className={styles.urlNamePopoverTag}>{tag.name}</Tag>
            ))}
          </div>
        }
        title="全部标签"
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
  runtimeReady,
  selectedTaskIds,
  onSelectedTaskIdsChange,
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
  runtimeReady: boolean
  selectedTaskIds: string[]
  onSelectedTaskIdsChange: (ids: string[]) => void
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
  const canRun = runtimeReady && isIdle && !task.is_skip
  const hasUrls = task.urls.length > 0
  const canUrlRun = runtimeReady && canRun && hasUrls
  const canEditOrDelete = runtimeReady && isIdle
  const canToggle = runtimeReady && isIdle
  const isSelectable = runtimeReady && isIdle && !task.is_skip
  const canStop = runtimeReady && (runtimeStatus === 'queued' || runtimeStatus === 'running') && Boolean(runtime?.latest_run_id)
  const canRestart = runtimeReady && runtimeStatus === 'stopped' && Boolean(runtime?.latest_run_id)

  const toggleSelected = (checked: boolean) => {
    onSelectedTaskIdsChange(
      checked
        ? [...selectedTaskIds, task.id]
        : selectedTaskIds.filter((id) => id !== task.id),
    )
  }

  const runItems: MenuProps['items'] = [
    { key: 'incremental', label: '增量爬取', icon: <PlayCircleOutlined /> },
    { key: 'full', label: '全量爬取', icon: <PlayCircleOutlined /> },
  ]

  return (
    <article className={task.is_skip ? `${styles.taskCard} ${styles.taskCardDisabled}` : styles.taskCard}>
      <div className={styles.taskCardHead}>
        <Checkbox
          aria-label={`选择 ${task.name}`}
          checked={selectedTaskIds.includes(task.id)}
          disabled={!isSelectable}
          onChange={(event) => toggleSelected(event.target.checked)}
        />
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
          <span className={styles.taskMetaLabel}>任务标签</span>
          <TaskTagTags tags={task.tags ?? []} />
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
        <div className={styles.taskCardPrimaryActions}>
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
          {runtimeReady && (
            <Button
              size="small"
              icon={<PlayCircleOutlined />}
              disabled={!canUrlRun}
              onClick={() => onUrlRun(task)}
            >
              URL 爬取
            </Button>
          )}
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
        </div>
        {canEditOrDelete ? (
          <div className={styles.taskCardMaintenanceActions}>
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
          </div>
        ) : (
          <div className={styles.taskCardMaintenanceActions} aria-hidden="true" />
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
  runtimeReady,
  tagOptions,
  selectedTagNames,
  onTagFilterChange,
  selectedTaskIds,
  onSelectedTaskIdsChange,
  onBatchRunClick,
  batchRunLoading,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
  onStop,
  onRestart,
  onUrlRun,
  onTemporaryTaskClick,
  onBatchTaskClick,
  current,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: TaskListCardsProps) {
  const navigate = useNavigate()
  return (
    <div className={styles.taskListShell}>
      <div className={styles.taskListToolbar}>
        <Space size={12} wrap>
          <Typography.Text type="secondary">
            {runtimeReady ? `共 ${total} 条` : '同步中'}
          </Typography.Text>
          <Select
            aria-label="标签筛选"
            mode="multiple"
            allowClear
            placeholder="标签筛选"
            value={selectedTagNames}
            options={tagOptions.map((tag) => ({ value: tag.name, label: tag.name }))}
            onChange={onTagFilterChange}
            className={styles.taskTagFilter}
          />
        </Space>
        <Space wrap>
          <Typography.Text type="secondary">已选 {selectedTaskIds.length} 个</Typography.Text>
          <Button
            disabled={selectedTaskIds.length === 0}
            loading={batchRunLoading}
            onClick={onBatchRunClick}
          >
            批量爬取
          </Button>
          <Button onClick={onTemporaryTaskClick}>
            临时任务
          </Button>
          <Button onClick={onBatchTaskClick}>
            批量新建
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
                runtimeReady={runtimeReady}
                selectedTaskIds={selectedTaskIds}
                onSelectedTaskIdsChange={onSelectedTaskIdsChange}
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

      {total > 0 && (
        <div className={styles.paginationBar}>
          <Pagination
            current={current}
            pageSize={pageSize}
            total={total}
            showSizeChanger
            pageSizeOptions={['10', '20', '50', '100']}
            showTotal={(count) => `共 ${count} 条`}
            onChange={(page, size) => {
              onPageChange(page)
              if (size !== pageSize) {
                onPageSizeChange(size)
              }
            }}
          />
        </div>
      )}
    </div>
  )
}

export default TaskListCards
