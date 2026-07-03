import {
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Empty, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { CrawlTask, TaskRuntimeStatus } from '@/api/crawlTask/types'
import type { CrawlMode } from '@/api/crawlerRun/types'
import styles from '../TaskPages.module.less'

type TaskListCardsProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  runtimeStatuses: Map<string, TaskRuntimeStatus>
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
  onStop: (task: CrawlTask) => void
}


const runtimeStatusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '待执行', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  success: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
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

function runtimeStatusTag(status: string | null) {
  if (!status) return <Typography.Text type="secondary">-</Typography.Text>
  const statusConfig = runtimeStatusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function TaskCard({
  task,
  runtimeStatus,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
  onStop,
}: {
  task: CrawlTask
  runtimeStatus: TaskRuntimeStatus | undefined
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
  onStop: (task: CrawlTask) => void
}) {
  const urlNames = getUrlNames(task)
  const isRunning = runtimeStatus?.status === 'running'
  const runItems: MenuProps['items'] = [
    { key: 'incremental', label: '增量爬取', icon: <PlayCircleOutlined />, disabled: isRunning },
    { key: 'full', label: '全量爬取', icon: <PlayCircleOutlined />, disabled: isRunning },
  ]

  return (
    <article className={task.is_skip ? `${styles.taskCard} ${styles.taskCardDisabled}` : styles.taskCard}>
      <div className={styles.taskCardHead}>
        <Tooltip title={task.name}>
          <Typography.Text strong className={styles.taskCardTitle}>
            {task.name}
          </Typography.Text>
        </Tooltip>
          {runtimeStatusTag(runtimeStatus?.status ?? null)}
      </div>

      <div className={styles.taskCardBody}>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>网盘路径</span>
          <Typography.Text className={styles.taskMetaValue}>{task.storage_location || '-'}</Typography.Text>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>URL 名称</span>
          <div className={styles.urlNameList}>
            {urlNames.length > 0
              ? urlNames.map((name, index) => <Tag key={`${name}-${index}`}>{name}</Tag>)
              : <Typography.Text type="secondary">-</Typography.Text>}
          </div>
        </div>
        <div className={styles.taskMetaRow}>
          <span className={styles.taskMetaLabel}>最后爬取时间</span>
          <Typography.Text className={styles.taskMetaValue}>{formatDateTime(task.last_run_at)}</Typography.Text>
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
            />

          </Space>
        </div>
      </div>

      <div className={styles.taskCardFooter}>
        {isRunning ? (
          <Button
            type="primary"
            danger
            size="small"
            icon={<StopOutlined />}
            onClick={() => onStop(task)}
          >
            停止
          </Button>
        ) : (
          <Dropdown
            menu={{
              items: runItems,
              onClick: ({ key }) => onRun(task, key as CrawlMode),
            }}
            trigger={['click']}
            disabled={task.is_skip}
          >
            <Button type="primary" size="small" icon={<PlayCircleOutlined />} disabled={task.is_skip}>
              爬取
            </Button>
          </Dropdown>
        )}
        <Space size={4}>
          <Tooltip title="编辑">
            <Button
              aria-label={`编辑 ${task.name}`}
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(task)}
              disabled={isRunning}
            />
          </Tooltip>
          <Tooltip title={isRunning ? '任务运行中，无法删除' : '删除'}>
            <Button
              aria-label={`删除 ${task.name}`}
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => onDelete(task)}
              disabled={isRunning}
            />
          </Tooltip>
          <Dropdown
            menu={{
              items: [
                { key: 'edit', label: '编辑', icon: <EditOutlined />, disabled: isRunning },
                { key: 'delete', label: '删除', icon: <DeleteOutlined />, danger: true, disabled: isRunning },
              ],
              onClick: ({ key }) => {
                if (key === 'edit') onEdit(task)
                if (key === 'delete') onDelete(task)
              },
            }}
            trigger={['click']}
          >
            <Button aria-label={`更多 ${task.name}`} type="text" size="small" icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      </div>
    </article>
  )
}

function TaskListCards({
  tasks,
  loading,
  total,
  runtimeStatuses,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
  onStop,
}: TaskListCardsProps) {
  return (
    <div className={styles.taskListShell}>
      <div className={styles.taskListToolbar}>
        <Typography.Text type="secondary">共 {total} 条</Typography.Text>
      </div>

      <Spin spinning={loading}>
        {tasks.length > 0 ? (
          <div className={styles.taskGrid}>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                runtimeStatus={runtimeStatuses.get(task.id)}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleSkip={onToggleSkip}
                onRun={onRun}
                onStop={onStop}
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
