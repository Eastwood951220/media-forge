import { useEffect, useState } from 'react'
import { Form, Button, Divider, Spin } from 'antd'
import { useNavigate } from '@tanstack/react-router'
import { getInitConfig } from '@/api/init'
import type { ConnectionTestResult, InitConfigRequest } from '@/api/init/types'
import { useInitConnectionTests } from './hooks/useInitConnectionTests'
import { useInitSubmit } from './hooks/useInitSubmit'
import { PostgresConfigSection } from './components/PostgresConfigSection'
import { RedisConfigSection } from './components/RedisConfigSection'
import styles from './InitPage.module.less'

function InitPage() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(true)
  const [form] = Form.useForm<InitConfigRequest>()

  useEffect(() => {
    getInitConfig()
      .then((res) => {
        if (res.databaseConfigured && res.redisConfigured) {
          void navigate({ to: '/login', search: { redirect: undefined } })
        }
      })
      .catch(() => {
        // Config not available, stay on init page
      })
      .finally(() => setChecking(false))
  }, [navigate])
  const { pgTesting, redisTesting, pgResult, redisResult, handleTestPg, handleTestRedis } =
    useInitConnectionTests(form)
  const { loading, handleFinish } = useInitSubmit()

  const testResultClass = (res: ConnectionTestResult | null): string =>
    res ? (res.success ? styles.success : styles.fail) : ''

  if (checking) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <Spin size="large" />
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>初始化配置</h1>
        <p className={styles.subtitle}>首次运行需要配置 PostgreSQL 和 Redis 连接信息</p>
        <Form<InitConfigRequest>
          form={form}
          layout="vertical"
          onFinish={(values) => { void handleFinish(values) }}
          initialValues={{
            databaseHost: 'localhost',
            databasePort: 54329,
            databaseName: 'mediaforge',
            databaseUser: 'admin',
            databasePassword: 'admin123',
            postgresConnectTimeout: 5,
            postgresPoolSize: 5,
            postgresMaxOverflow: 10,
            postgresMaxRetries: 10,
            postgresRetryDelay: 3,
            redisHost: 'localhost',
            redisPort: 6379,
            redisPassword: 'redis123',
            redisSocketTimeout: 5,
            redisConnectTimeout: 5,
            redisMaxConnections: 10,
          }}
        >
          <PostgresConfigSection />

          <div className={styles.testBar}>
            <Button onClick={() => { void handleTestPg() }} loading={pgTesting}>
              测试 PostgreSQL 连接
            </Button>
            {pgResult && (
              <span className={`${styles.testResult} ${testResultClass(pgResult)}`}>
                {pgResult.message}
              </span>
            )}
          </div>

          <Divider />

          <RedisConfigSection />

          <div className={styles.testBar}>
            <Button onClick={() => { void handleTestRedis() }} loading={redisTesting}>
              测试 Redis 连接
            </Button>
            {redisResult && (
              <span className={`${styles.testResult} ${testResultClass(redisResult)}`}>
                {redisResult.message}
              </span>
            )}
          </div>

          <Divider />

          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            className={styles.submitBtn}
            size="large"
          >
            保存并进入登录页
          </Button>
        </Form>
      </div>
    </div>
  )
}

export default InitPage
