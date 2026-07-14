import { Link } from '@tanstack/react-router'
import { Empty, Tabs, Tag } from 'antd'
import type { DashboardOverview } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusLabels: Record<string, { text: string; color: string }> = {
  queued: { text: '排队中', color: 'default' },
  running: { text: '运行中', color: 'processing' },
  completed: { text: '已完成', color: 'success' },
  failed: { text: '失败', color: 'error' },
  stopped: { text: '已停止', color: 'warning' },
}

function tagFor(status: string) {
  const meta = statusLabels[status] ?? { text: status, color: 'default' }
  return <Tag color={meta.color}>{meta.text}</Tag>
}

export function DashboardRecentTabs({ overview }: { overview: DashboardOverview }) {
  return (
    <article className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>最近工作</h2>
      </div>
      <Tabs
        items={[
          {
            key: 'runs',
            label: '最近采集运行',
            children: overview.runs.recent.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无采集运行" />
            ) : (
              <div className={styles.recentList}>
                {overview.runs.recent.map((run) => (
                  <div className={styles.recentRow} key={run.id}>
                    <div>
                      <Link to="/crawler/runs/$id" params={{ id: run.id }}>{run.task_name}</Link>
                      <span>{new Date(run.created_at ?? '').toLocaleString()}</span>
                    </div>
                    {tagFor(run.status)}
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: 'storage',
            label: '最近存储任务',
            children: overview.storage.recent_tasks.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无存储任务" />
            ) : (
              <div className={styles.recentList}>
                {overview.storage.recent_tasks.map((task) => (
                  <div className={styles.recentRow} key={task.id}>
                    <div>
                      <Link to="/storage/tasks/$id" params={{ id: task.id }}>{task.display_name}</Link>
                      <span>{new Date(task.created_at ?? '').toLocaleString()}</span>
                    </div>
                    {tagFor(task.status)}
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </article>
  )
}
