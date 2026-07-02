import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  FieldTimeOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import styles from './DashboardPage.module.less'

const metrics = [
  {
    label: 'Active jobs',
    value: '18',
    detail: '6 rendering, 12 encoding',
    icon: <ThunderboltOutlined />,
  },
  {
    label: 'Queued assets',
    value: '142',
    detail: 'Across 4 processing lanes',
    icon: <FieldTimeOutlined />,
  },
  {
    label: 'Storage used',
    value: '67%',
    detail: '18.4 TB available',
    icon: <DatabaseOutlined />,
  },
]

const lanes = [
  { name: 'Ingest', status: 'Healthy', load: '24 jobs' },
  { name: 'Transcode', status: 'Busy', load: '58 jobs' },
  { name: 'Review', status: 'Healthy', load: '12 jobs' },
]

const activity = [
  'Trailer batch completed',
  'Proxy generation started',
  'Archive sync verified',
]

function DashboardPage() {
  return (
    <div className={styles.dashboard}>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>Media pipeline health</p>
          <h1 className={styles.title}>Operations Console</h1>
          <p className={styles.summary}>
            Monitor processing load, asset movement, and service readiness from one workspace.
          </p>
        </div>
        <div className={styles.heroStatus}>
          <span className={styles.statusIcon}>
            <CheckCircleOutlined />
          </span>
          <div>
            <span className={styles.statusLabel}>System status</span>
            <strong>Healthy</strong>
          </div>
        </div>
      </section>

      <section className={styles.metricsGrid}>
        {metrics.map((metric) => (
          <article key={metric.label} className={styles.metricCard}>
            <span className={styles.metricIcon}>{metric.icon}</span>
            <div>
              <span className={styles.metricLabel}>{metric.label}</span>
              <strong className={styles.metricValue}>{metric.value}</strong>
              <span className={styles.metricDetail}>{metric.detail}</span>
            </div>
          </article>
        ))}
      </section>

      <section className={styles.workGrid}>
        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.panelKicker}>Workload</span>
              <h2>Processing lanes</h2>
            </div>
            <CloudServerOutlined className={styles.panelIcon} />
          </div>
          <div className={styles.laneList}>
            {lanes.map((lane) => (
              <div key={lane.name} className={styles.laneRow}>
                <span>{lane.name}</span>
                <strong>{lane.status}</strong>
                <em>{lane.load}</em>
              </div>
            ))}
          </div>
        </article>

        <article className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <span className={styles.panelKicker}>Timeline</span>
              <h2>Recent activity</h2>
            </div>
            <ApiOutlined className={styles.panelIcon} />
          </div>
          <div className={styles.activityList}>
            {activity.map((item) => (
              <div key={item} className={styles.activityRow}>
                <span className={styles.activityDot} />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}

export default DashboardPage
