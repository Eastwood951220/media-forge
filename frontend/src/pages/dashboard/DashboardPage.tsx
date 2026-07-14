import { Alert, Button, Skeleton } from 'antd'
import { DashboardAlerts } from './components/DashboardAlerts'
import { DashboardCharts } from './components/DashboardCharts'
import { DashboardMetricCards } from './components/DashboardMetricCards'
import { DashboardRecentTabs } from './components/DashboardRecentTabs'
import { DashboardStatusHeader } from './components/DashboardStatusHeader'
import { useDashboardOverview } from './hooks/useDashboardOverview'
import styles from './DashboardPage.module.less'

function DashboardPage() {
  const { data, loading, error, refreshing, refresh } = useDashboardOverview()

  if (loading && !data) {
    return (
      <div className={styles.dashboard}>
        <Skeleton active paragraph={{ rows: 3 }} />
        <section className={styles.metricsGrid}>
          <Skeleton active />
          <Skeleton active />
          <Skeleton active />
          <Skeleton active />
        </section>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className={styles.dashboard}>
        <Alert
          type="error"
          showIcon
          message="首页数据加载失败"
          description={error.message}
        />
        <Button onClick={refresh}>重试</Button>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className={styles.dashboard}>
      <DashboardStatusHeader
        status={data.system_status}
        refreshedAt={data.refreshed_at}
        refreshing={refreshing}
        onRefresh={refresh}
      />
      {data.partial_errors.length > 0 ? (
        <Alert type="warning" showIcon message="部分数据降级" description="部分模块暂时无法读取，页面已展示可用数据。" />
      ) : null}
      <DashboardMetricCards overview={data} />
      <DashboardCharts distribution={data.runs.status_distribution} trend={data.runs.daily_trend} />
      <section className={styles.workGrid}>
        <DashboardRecentTabs overview={data} />
        <DashboardAlerts alerts={data.alerts} />
      </section>
    </div>
  )
}

export default DashboardPage
