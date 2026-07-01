import { useState } from 'react'
import { Form, Input, InputNumber, Button, Divider, message } from 'antd'
import { saveInitConfig, testPostgres, testRedis } from '@/api/init'
import type {
  ConnectionTestResult,
  InitConfigRequest,
  PostgresTestParams,
  RedisTestParams,
} from '@/api/init/types'
import styles from './InitPage.module.less'

function InitPage() {
  const [loading, setLoading] = useState(false)
  const [pgTesting, setPgTesting] = useState(false)
  const [redisTesting, setRedisTesting] = useState(false)
  const [pgResult, setPgResult] = useState<ConnectionTestResult | null>(null)
  const [redisResult, setRedisResult] = useState<ConnectionTestResult | null>(null)

  const [form] = Form.useForm<InitConfigRequest>()

  const getPgTestParams = (): PostgresTestParams => {
    const v = form.getFieldsValue()
    return {
      host: v.databaseHost,
      port: v.databasePort,
      database: v.databaseName,
      user: v.databaseUser,
      password: v.databasePassword,
      connect_timeout: v.postgresConnectTimeout,
    }
  }

  const getRedisTestParams = (): RedisTestParams => {
    const v = form.getFieldsValue()
    return {
      host: v.redisHost,
      port: v.redisPort,
      password: v.redisPassword,
      socket_timeout: v.redisSocketTimeout,
      connect_timeout: v.redisConnectTimeout,
    }
  }

  const handleTestPg = async () => {
    setPgTesting(true)
    setPgResult(null)
    try {
      const res = await testPostgres(getPgTestParams())
      setPgResult(res as ConnectionTestResult)
    } catch {
      setPgResult({ success: false, message: '测试请求失败' })
    } finally {
      setPgTesting(false)
    }
  }

  const handleTestRedis = async () => {
    setRedisTesting(true)
    setRedisResult(null)
    try {
      const res = await testRedis(getRedisTestParams())
      setRedisResult(res as ConnectionTestResult)
    } catch {
      setRedisResult({ success: false, message: '测试请求失败' })
    } finally {
      setRedisTesting(false)
    }
  }

  const handleFinish = async (values: InitConfigRequest) => {
    setLoading(true)
    try {
      // Auto-test both connections before saving
      const [pgRes, redisRes] = await Promise.all([
        testPostgres({
          host: values.databaseHost,
          port: values.databasePort,
          database: values.databaseName,
          user: values.databaseUser,
          password: values.databasePassword,
          connect_timeout: values.postgresConnectTimeout,
        }),
        testRedis({
          host: values.redisHost,
          port: values.redisPort,
          password: values.redisPassword,
          socket_timeout: values.redisSocketTimeout,
          connect_timeout: values.redisConnectTimeout,
        }),
      ])

      const pgOk = (pgRes as ConnectionTestResult).success
      const redisOk = (redisRes as ConnectionTestResult).success

      if (!pgOk || !redisOk) {
        const msgs: string[] = []
        if (!pgOk) msgs.push('PostgreSQL: ' + (pgRes as ConnectionTestResult).message)
        if (!redisOk) msgs.push('Redis: ' + (redisRes as ConnectionTestResult).message)
        void message.error(msgs.join('\n'))
        return
      }

      // Both passed — save configuration
      await saveInitConfig(values)
      void message.success('配置保存成功！正在跳转...')
      setTimeout(() => {
        window.location.href = '/login'
      }, 1500)
    } catch {
      void message.error('配置保存失败')
    } finally {
      setLoading(false)
    }
  }

  const testResultClass = (res: ConnectionTestResult | null): string =>
    res ? (res.success ? styles.success : styles.fail) : ''

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
            databasePort: 5432,
            databaseName: 'mediaforge',
            databaseUser: 'postgres',
            databasePassword: 'postgres',
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
          {/* PostgreSQL Section */}
          <div className={styles.section}>
            <h3>PostgreSQL 数据库配置</h3>
            <div className={styles.row}>
              <Form.Item name="databaseHost" label="主机地址" rules={[{ required: true }]}>
                <Input placeholder="localhost" />
              </Form.Item>
              <Form.Item name="databasePort" label="端口" rules={[{ required: true }]}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <div className={styles.row}>
              <Form.Item name="databaseUser" label="用户名" rules={[{ required: true }]}>
                <Input placeholder="postgres" />
              </Form.Item>
              <Form.Item name="databasePassword" label="密码">
                <Input.Password placeholder="postgres" />
              </Form.Item>
            </div>
            <Form.Item name="databaseName" label="数据库名" rules={[{ required: true }]}>
              <Input placeholder="mediaforge" />
            </Form.Item>
            <div className={styles.row}>
              <Form.Item name="postgresConnectTimeout" label="连接超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="postgresPoolSize" label="连接池大小">
                <InputNumber min={1} max={50} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <div className={styles.row}>
              <Form.Item name="postgresMaxOverflow" label="额外连接数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="postgresMaxRetries" label="启动重试次数">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="postgresRetryDelay" label="重试间隔(秒)">
              <InputNumber min={0} max={60} style={{ width: '100%' }} />
            </Form.Item>
          </div>

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

          {/* Redis Section */}
          <div className={styles.section}>
            <h3>Redis 配置</h3>
            <div className={styles.row}>
              <Form.Item name="redisHost" label="主机地址" rules={[{ required: true }]}>
                <Input placeholder="localhost" />
              </Form.Item>
              <Form.Item name="redisPort" label="端口" rules={[{ required: true }]}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="redisPassword" label="密码（可选）">
              <Input.Password placeholder="留空表示无密码" />
            </Form.Item>
            <div className={styles.row}>
              <Form.Item name="redisSocketTimeout" label="响应超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="redisConnectTimeout" label="连接超时(秒)">
                <InputNumber min={1} max={60} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item name="redisMaxConnections" label="最大连接数">
              <InputNumber min={1} max={200} style={{ width: '100%' }} />
            </Form.Item>
          </div>

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
