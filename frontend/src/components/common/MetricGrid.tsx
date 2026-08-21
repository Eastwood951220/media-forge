import { clsx } from 'clsx'
import type { ReactNode } from 'react'
import styles from './MetricGrid.module.less'

export interface MetricTileProps {
  key: string
  label: ReactNode
  value: ReactNode
  tone?: 'default' | 'success' | 'info' | 'warning' | 'danger'
}

export interface MetricGridProps {
  items: MetricTileProps[]
  className?: string
}

export function MetricGrid({ items, className }: MetricGridProps) {
  return (
    <div className={clsx(styles.grid, className)}>
      {items.map((item) => (
        <div
          key={item.key}
          className={clsx(styles.tile, item.tone && styles[item.tone])}
        >
          <span className={styles.label}>{item.label}</span>
          <span className={styles.value}>{item.value}</span>
        </div>
      ))}
    </div>
  )
}
