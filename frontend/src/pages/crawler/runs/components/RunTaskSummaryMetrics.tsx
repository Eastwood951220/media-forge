import AnimatedNumber from '@/components/AnimatedNumber'
import { MetricGrid } from '@/components/common'
import type { RunTaskSummary } from '@/api/crawler/crawlerRun/types'

interface RunTaskSummaryMetricsProps {
  summary: RunTaskSummary
}

function RunTaskSummaryMetrics({ summary }: RunTaskSummaryMetricsProps) {
  return (
    <MetricGrid
      items={[
        {
          key: 'total',
          label: '总数',
          value: <AnimatedNumber value={Number(summary.total)} duration={1.5} separator="," />,
          tone: 'default',
        },
        {
          key: 'completed',
          label: '完成',
          value: <AnimatedNumber value={Number(summary.completed)} duration={1.5} separator="," />,
          tone: 'success',
        },
        {
          key: 'waiting',
          label: '等待',
          value: <AnimatedNumber value={Number(summary.waiting)} duration={1.5} separator="," />,
          tone: 'info',
        },
        {
          key: 'skipped',
          label: '跳过',
          value: <AnimatedNumber value={Number(summary.skipped)} duration={1.5} separator="," />,
          tone: 'warning',
        },
        {
          key: 'failed',
          label: '失败',
          value: <AnimatedNumber value={Number(summary.failed)} duration={1.5} separator="," />,
          tone: 'danger',
        },
      ]}
    />
  )
}

export default RunTaskSummaryMetrics
