import { useEffect, useMemo, useRef } from 'react'
import { Chart } from '@antv/g2'
import { Empty } from 'antd'
import type { CountItem, DailyTrendItem } from '@/api/dashboard/types'
import styles from '../DashboardPage.module.less'

const statusColor: Record<string, string> = {
  queued: '#1677ff',
  running: '#1677ff',
  completed: '#52c41a',
  failed: '#ff4d4f',
  stopped: '#faad14',
  skipped: '#8c8c8c',
}

function StatusDistributionChart({ data }: { data: CountItem[] }) {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!ref.current || data.length === 0) return
    const chart = new Chart({ container: ref.current, autoFit: true, height: 220 })
    chart
      .interval()
      .data(data)
      .encode('x', 'status')
      .encode('y', 'count')
      .encode('color', 'status')
      .scale('color', { range: data.map((item) => statusColor[item.status] ?? '#8c8c8c') })
    chart.render()
    return () => {
      chart.destroy()
    }
  }, [data])

  if (data.length === 0) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行状态数据" />
  return <div ref={ref} className={styles.chartCanvas} />
}

function TrendChart({ data }: { data: DailyTrendItem[] }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const chartData = useMemo(
    () => data.flatMap((item) => [
      { date: item.date, type: '已完成', value: item.completed },
      { date: item.date, type: '失败', value: item.failed },
    ]),
    [data],
  )

  useEffect(() => {
    if (!ref.current || chartData.length === 0 || chartData.every((item) => item.value === 0)) return
    const chart = new Chart({ container: ref.current, autoFit: true, height: 220 })
    chart
      .line()
      .data(chartData)
      .encode('x', 'date')
      .encode('y', 'value')
      .encode('color', 'type')
      .scale('color', { range: ['#52c41a', '#ff4d4f'] })
    chart.render()
    return () => {
      chart.destroy()
    }
  }, [chartData])

  if (chartData.length === 0 || chartData.every((item) => item.value === 0)) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无近 7 天趋势数据" />
  }
  return <div ref={ref} className={styles.chartCanvas} />
}

export function DashboardCharts({ distribution, trend }: { distribution: CountItem[]; trend: DailyTrendItem[] }) {
  return (
    <section className={styles.chartGrid}>
      <article className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>运行状态分布</h2>
        </div>
        <StatusDistributionChart data={distribution} />
      </article>
      <article className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>近 7 天采集结果</h2>
        </div>
        <TrendChart data={trend} />
      </article>
    </section>
  )
}
