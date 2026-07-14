import {
  CloudSyncOutlined,
  DatabaseOutlined,
  UnorderedListOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Alert } from 'antd'
import type { DashboardOverview, PartialError } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

function sectionError(partialErrors: PartialError[], section: string) {
  return partialErrors.find((item) => item.section === section || item.section.startsWith(`${section}.`))
}

export function DashboardMetricCards({ overview }: { overview: DashboardOverview }) {
  const stored = overview.content.storage_status.stored
  const movieTotal = overview.content.movie_total
  const storedRatio = movieTotal > 0 ? Math.round((stored / movieTotal) * 100) : 0
  const cards = [
    {
      key: 'crawler',
      title: '采集队列',
      value: `${overview.crawler.runtime_stats.running} / ${overview.crawler.queue.queue_size}`,
      detail: '运行中 / 排队',
      icon: <CloudSyncOutlined />,
    },
    {
      key: 'crawler',
      title: '任务配置',
      value: `${overview.crawler.task_stats.enabled} / ${overview.crawler.task_stats.total}`,
      detail: '启用 / 总任务',
      icon: <UnorderedListOutlined />,
    },
    {
      key: 'content',
      title: '影片库',
      value: `${movieTotal}`,
      detail: `已入库 ${storedRatio}%`,
      icon: <VideoCameraOutlined />,
    },
    {
      key: 'storage',
      title: '存储索引',
      value: `${overview.storage.index.video_count}`,
      detail: `${overview.storage.index.status} · ${overview.storage.index.category_count} 分类`,
      icon: <DatabaseOutlined />,
    },
  ]

  return (
    <section className={styles.metricsGrid}>
      {cards.map((card) => {
        const error = sectionError(overview.partial_errors, card.key)
        return (
          <article className={styles.metricCard} key={`${card.key}-${card.title}`}>
            <span className={styles.metricIcon}>{card.icon}</span>
            <div className={styles.metricBody}>
              <span className={styles.metricLabel}>{card.title}</span>
              <strong>{card.value}</strong>
              <span className={styles.metricDetail}>{card.detail}</span>
              {error ? <Alert type="warning" showIcon message={error.message} className={styles.partialError} /> : null}
            </div>
          </article>
        )
      })}
    </section>
  )
}
