import AnimatedNumber from '@/components/AnimatedNumber'
import type { RunTaskSummary } from '@/api/crawlerRun/types'
import styles from '../RunDetailPage.module.less'

interface RunTaskSummaryMetricsProps {
  summary: RunTaskSummary
}

function RunTaskSummaryMetrics({ summary }: RunTaskSummaryMetricsProps) {
  return (
    <div className={styles.summaryMetrics}>
      {[
        ['总数', summary.total, styles.metricTotal],
        ['完成', summary.completed, styles.metricCompleted],
        ['等待', summary.waiting, styles.metricWaiting],
        ['跳过', summary.skipped, styles.metricSkipped],
        ['失败', summary.failed, styles.metricFailed],
      ].map(([label, value, className]) => (
        <div key={label} className={`${styles.metricTile} ${className}`}>
          <div className={styles.metricLabel}>{label}</div>
          <div className={styles.metricValue}>
            <AnimatedNumber value={Number(value)} duration={1.5} separator="," />
          </div>
        </div>
      ))}
    </div>
  )
}

export default RunTaskSummaryMetrics
