import { Form, Input, InputNumber } from 'antd'
import styles from '../InitPage.module.less'

export function RedisConfigSection() {
  return (
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
  )
}
