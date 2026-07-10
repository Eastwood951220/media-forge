import { useEffect, useState } from 'react'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Space, Switch,
  Tag,
} from 'antd'
import {
  ApiOutlined,
  ClockCircleOutlined,
  CloudOutlined,
  FilterOutlined,
  FolderOutlined,
} from '@ant-design/icons'
import {
  fetchStorageConfig,
  testStorageConnection,
  updateStorageConfig,
  type StorageConfig,
  type StorageTestResult,
} from '@/api/storage/storageConfig'
import SectionTitle from './components/SectionTitle'
import SelectTags from './components/SelectTags'
import TestResultCard from './components/TestResultCard'
import { getErrorMessage } from './utils/error'
import styles from './StorageConfigPage.module.less'

export default function StorageConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm<StorageConfig>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<StorageTestResult | null>(null)
  const [tokenInput, setTokenInput] = useState('')

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await fetchStorageConfig()
      form.setFieldsValue(data)
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadConfig()
  }, [])

  const handleSave = async (values: StorageConfig) => {
    setSaving(true)
    try {
      const payload = { ...values }
      if (tokenInput) {
        payload.api_token = tokenInput
      } else {
        delete (payload as Partial<StorageConfig>).api_token
      }
      const updated = await updateStorageConfig(payload)
      form.setFieldsValue(updated)
      setTokenInput('')
      message.success('存储配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await testStorageConnection())
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setTesting(false)
    }
  }

  const maskedToken = Form.useWatch('api_token', form)

  if (loading) return null

  return (
    <div className={styles.page}>
      <Form form={form} layout="vertical" onFinish={(values) => void handleSave(values)}>
        <Card
          title={<SectionTitle icon={<CloudOutlined />} text="服务配置" />}
          className={styles.formCard}
        >
          <Form.Item
            name="grpc_host"
            label="gRPC 主机地址"
            rules={[{ required: true, message: '请输入 gRPC 主机地址' }]}
          >
            <Input placeholder="localhost:9798" />
          </Form.Item>
          <Form.Item label="API Token">
            <div className={styles.tokenStack}>
              {maskedToken && <Tag color="blue">当前已配置: {maskedToken}</Tag>}
              <Input.Password
                placeholder="输入新的 API Token（留空则不修改）"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
              />
            </div>
          </Form.Item>
          <Form.Item name="request_timeout_seconds" label="请求超时 (秒)">
            <InputNumber min={1} max={300} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="connect_timeout_seconds" label="连接超时 (秒)">
            <InputNumber min={1} max={60} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<FolderOutlined />} text="目录配置" />}
          className={styles.formCard}
        >
          <Form.Item
            name="download_root_folder"
            label="下载根目录"
            rules={[{ required: true, message: '请输入下载根目录' }]}
          >
            <Input placeholder="/Downloads" />
          </Form.Item>
          <Form.Item
            name="target_folder"
            label="目标文件夹"
            rules={[{ required: true, message: '请输入目标文件夹' }]}
          >
            <Input placeholder="/Movies" />
          </Form.Item>
          <Form.Item name="use_task_subfolder" label="使用任务子文件夹" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="auto_create_target_folder" label="自动创建目标文件夹" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<ClockCircleOutlined />} text="任务执行" />}
          className={styles.formCard}
        >
          <Form.Item name="operation_delay_min" label="操作最小延迟 (秒)">
            <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="operation_delay_max" label="操作最大延迟 (秒)">
            <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="download_poll_interval_min" label="下载轮询最小间隔 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="download_poll_interval_max" label="下载轮询最大间隔 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retry_delay_min" label="重试最小延迟 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="retry_delay_max" label="重试最大延迟 (秒)">
            <InputNumber min={0} max={120} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_step_retries" label="最大重试次数">
            <InputNumber min={0} max={20} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="download_max_poll_count"
            label="下载轮询最大次数"
            tooltip="超过此次数将跳过当前任务，进入下一个任务"
          >
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="magnet_max_attempts_per_subtask"
            label="每个子任务最多尝试磁力条数"
            tooltip="当前磁力下载轮询超过最大次数后，才会尝试下一条磁力；超过此条数后子任务失败"
          >
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card
          title={<SectionTitle icon={<FilterOutlined />} text="文件筛选" />}
          className={styles.formCard}
        >
          <Form.Item name="minimum_video_size_mb" label="最小视频大小 (MB)">
            <InputNumber min={0} max={10000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="video_extensions" label="视频扩展名" tooltip="输入扩展名后按回车添加">
            <SelectTags placeholder="例如: .mp4, .mkv" />
          </Form.Item>
        </Card>

        <Card title="操作" className={styles.formCard}>
          <Space className={styles.actions}>
            <Button icon={<ApiOutlined />} onClick={() => void handleTest()} loading={testing}>
              测试连接
            </Button>
            <Button type="primary" htmlType="submit" loading={saving}>
              保存配置
            </Button>
            <Button onClick={() => void loadConfig()}>重置</Button>
          </Space>
        </Card>
      </Form>

      {testResult && <TestResultCard result={testResult} />}
    </div>
  )
}
