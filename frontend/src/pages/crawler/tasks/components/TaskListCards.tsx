import {
  DeleteOutlined,
  EditOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Empty, Input, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd'
import type { MenuProps } from 'antd'
import type { CrawlTask } from '@/api/crawlTask/types'
import type { CrawlMode } from '@/api/crawlerRun/types'
import styles from '../TaskPages.module.less'

type TaskListCardsProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  keyword: string
  onKeywordChange: (keyword: string) => void
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
}

const taskStatusLabels: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'default' },
  running: { text: '爬取中', color: 'processing' },
  success: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
}

const runStatusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
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

function statusTag(status: string) {
  const statusConfig = taskStatusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function runStatusTag(status: string | null) {
  if (!status) return <Typography.Text type="secondary">-</Typography.Text>
  const statusConfig = runStatusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
}

function TaskCard({
  task,
  onEdit,
  onDelete,
  onToggleSkip,
  onRun,
}: {
  task: CrawlTask
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onToggleSkip: (task: CrawlTask) => void
  onRun: (task: CrawlTask, mode: CrawlMode) => void
}) {
  const urlNames = getUrlNames(task)
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
        {statusTag(task.status)}
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
            {runStatusTag(task.last_run_status)}
          </Space>
        </div>
      </div>

      <div className={styles.taskCardFooter}>
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
          <Dropdown
            menu={{
              items: [
                { key: 'edit', label: '编辑', icon: <EditOutlined /> },
                { key: 'delete', label: '删除', icon: <DeleteOutlined />, danger: true },
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
  keyword,
  onKeywordChange,
  onEdit,
  onDelete,
  onToggleSkip,
  onSearch,
  onRun,
}: TaskListCardsProps) {
  return (
    <div className={styles.taskListShell}>
      <div className={styles.taskListToolbar}>
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          className={styles.taskSearch}
        />
        <Typography.Text type="secondary">共 {total} 条</Typography.Text>
      </div>

      <Spin spinning={loading}>
        {tasks.length > 0 ? (
          <div className={styles.taskGrid}>
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onEdit={onEdit}
                onDelete={onDelete}
                onToggleSkip={onToggleSkip}
                onRun={onRun}
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
