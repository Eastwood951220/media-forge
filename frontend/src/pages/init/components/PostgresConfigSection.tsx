import { Form, Input, InputNumber } from 'antd'
import styles from '../InitPage.module.less'

export function PostgresConfigSection() {
  return (
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
  )
}
