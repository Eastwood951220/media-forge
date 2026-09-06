import { useMemo, useState } from 'react'
import { Empty, Segmented } from 'antd'
import type { DashboardContentRankings as ContentRankings, DashboardRankingGroup, RankingItem } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

type RankingMode = keyof ContentRankings

const modeOptions: Array<{ label: string; value: RankingMode }> = [
  { label: '总排名', value: 'total' },
  { label: '最近存储', value: 'recent_storage' },
  { label: '最近入库', value: 'recent_created' },
]

const dimensionLabels: Array<{ key: keyof DashboardRankingGroup; title: string }> = [
  { key: 'actors', title: '演员 Top 5' },
  { key: 'makers', title: '厂商 Top 5' },
  { key: 'tags', title: '标签 Top 5' },
  { key: 'series', title: '系列 Top 5' },
]

function RankingList({ items }: { items: RankingItem[] }) {
  const maxCount = useMemo(() => Math.max(...items.map((item) => item.count), 0), [items])

  if (items.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无排名数据" />
  }

  return (
    <ol className={styles.rankingList}>
      {items.map((item, index) => (
        <li className={styles.rankingItem} key={`${item.name}-${index}`}>
          <span className={styles.rankingIndex}>{index + 1}</span>
          <span className={styles.rankingName} title={item.name}>{item.name}</span>
          <span className={styles.rankingBar} aria-hidden="true">
            <span style={{ width: `${maxCount > 0 ? Math.max(8, Math.round((item.count / maxCount) * 100)) : 0}%` }} />
          </span>
          <strong>{item.count}</strong>
        </li>
      ))}
    </ol>
  )
}

export function DashboardContentRankings({ rankings }: { rankings: ContentRankings }) {
  const [mode, setMode] = useState<RankingMode>('total')
  const activeGroup = rankings[mode]

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2>内容排名</h2>
          <p className={styles.panelHint}>最近统计窗口为 30 天</p>
        </div>
        <Segmented<RankingMode>
          value={mode}
          options={modeOptions}
          onChange={setMode}
        />
      </div>
      <div className={styles.rankingGrid}>
        {dimensionLabels.map((dimension) => (
          <article className={styles.rankingCard} key={dimension.key}>
            <h3>{dimension.title}</h3>
            <RankingList items={activeGroup[dimension.key]} />
          </article>
        ))}
      </div>
    </section>
  )
}
