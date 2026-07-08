import { Alert, Form, Button, Divider } from 'antd'
import type { ConnectionTestResult, InitConfigRequest } from '@/api/init/types'
import { useInitConnectionTests } from './hooks/useInitConnectionTests'
import { useInitSubmit } from './hooks/useInitSubmit'
import { PostgresConfigSection } from './components/PostgresConfigSection'
import { RedisConfigSection } from './components/RedisConfigSection'
import styles from './InitPage.module.less'

function InitPage() {
  const [form] = Form.useForm<InitConfigRequest>()
  const { pgTesting, redisTesting, pgResult, redisResult, handleTestPg, handleTestRedis } =
    useInitConnectionTests(form)
  const { loading, handleFinish } = useInitSubmit()

  const testResultClass = (res: ConnectionTestResult | null): string =>
    res ? (res.success ? styles.success : styles.fail) : ''

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <h1 className={styles.title}>初始化配置</h1>
        <p className={styles.subtitle}>首次运行需要配置 PostgreSQL 和 Redis 连接信息</p>
        <Alert
          className={styles.dockerNotice}
          type="info"
          showIcon
          message="Docker 部署提示"
          description="在容器中 localhost/127.0.0.1 指向 Media Forge 容器自身。连接外部 PostgreSQL 或 Redis 时，请填写 fnOS 宿主机局域网 IP、外部服务地址，或同一 Docker 网络中的容器名。"
        />

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
            redisPassword: '',
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
