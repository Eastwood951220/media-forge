import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Spin,
  Tag,
} from 'antd'
import {
  ApiOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  getScrapingConfig,
  runScrapingStrm,
  updateScrapingConfig,
  type ScrapingConfig,
  type ScrapingConfigUpdate,
} from '@/api/scraping/scrapingConfig'
import { FullWidthNumberInput } from '@/components/common'
import { getErrorMessage, isFormValidationError } from './utils/error'
import styles from './ScrapingConfigPage.module.less'

type FormValues = {
  base_url: string
  api_key?: string
  directory_id: number
  trigger_delay_seconds: number
}

const DEFAULT_BASE_URL = 'http://192.168.0.36:12333'

export default function ScrapingConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false)
  const [maskedApiKey, setMaskedApiKey] = useState('')

  const applyConfig = useCallback(
    (config: ScrapingConfig) => {
      form.setFieldsValue({
        base_url: config.base_url,
        api_key: '',
        directory_id: config.directory_id ?? undefined,
        trigger_delay_seconds: config.trigger_delay_seconds,
      })
      setApiKeyConfigured(config.api_key_configured)
      setMaskedApiKey(config.api_key)
    },
    [form],
  )

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      applyConfig(await getScrapingConfig())
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [applyConfig, message])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial config load on mount is intentional.
    void loadConfig()
  }, [loadConfig])

  const buildPayload = (values: FormValues): ScrapingConfigUpdate => {
    const payload: ScrapingConfigUpdate = {
      base_url: values.base_url,
      directory_id: values.directory_id,
      trigger_delay_seconds: values.trigger_delay_seconds,
    }
    if (values.api_key?.trim()) {
      payload.api_key = values.api_key.trim()
    }
    return payload
  }

  const persist = async (values: FormValues): Promise<ScrapingConfig> => {
    const updated = await updateScrapingConfig(buildPayload(values))
    applyConfig(updated)
    return updated
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await persist(await form.validateFields())
      message.success('刮削配置已保存')
    } catch (error: unknown) {
      if (isFormValidationError(error)) return
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      await persist(await form.validateFields())
      const result = await runScrapingStrm()
      if (result.success) {
        message.success(result.message || 'STRM 生成已触发')
      } else {
        message.error(result.message || 'STRM 生成失败')
      }
    } catch (error: unknown) {
      if (isFormValidationError(error)) return
      message.error(getErrorMessage(error))
    } finally {
      setRunning(false)
    }
  }

  const delaySeconds = Form.useWatch('trigger_delay_seconds', form) ?? 30

  return (
    <div className={styles.page}>
      <Spin spinning={loading}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ base_url: DEFAULT_BASE_URL }}
        >
          <div className={styles.layout}>
            <div className={styles.mainPanel}>
              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <ApiOutlined />
                    服务配置
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="base_url"
                    label="服务地址"
                    rules={[{ required: true, message: '请输入外部服务地址' }]}
                  >
                    <Input placeholder={DEFAULT_BASE_URL} />
                  </Form.Item>

                  <Form.Item className={styles.fieldSpan2} label="API Key">
                    <div className={styles.tokenStack}>
                      {apiKeyConfigured && (
                        <Tag color="blue">已配置: {maskedApiKey}</Tag>
                      )}
                      <Form.Item
                        name="api_key"
                        noStyle
                        rules={[
                          {
                            validator: (_, value?: string) =>
                              apiKeyConfigured || value?.trim()
                                ? Promise.resolve()
                                : Promise.reject(new Error('请输入 API Key')),
                          },
                        ]}
                      >
                        <Input.Password placeholder="留空保持不变" />
                      </Form.Item>
                    </div>
                  </Form.Item>

                  <Form.Item
                    name="directory_id"
                    label="目录 ID"
                    rules={[{ required: true, message: '请输入目录 ID' }]}
                  >
                    <FullWidthNumberInput min={1} placeholder="4" />
                  </Form.Item>
                </div>
              </Card>

              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <ClockCircleOutlined />
                    自动触发
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="trigger_delay_seconds"
                    label="触发等待时间（秒）"
                    rules={[{ required: true, message: '请输入触发等待时间' }]}
                  >
                    <FullWidthNumberInput min={10} max={3600} />
                  </Form.Item>
                </div>
                <Alert
                  type="info"
                  showIcon
                  title={`存储队列空闲 ${delaySeconds} 秒后自动调用；等待期间有新任务会重新计时。`}
                />
              </Card>
            </div>

            <div className={styles.sidePanel}>
              <Card
                title="操作"
                className={`${styles.formCard} ${styles.actionCard}`}
              >
                <div className={styles.actions}>
                  <Button
                    type="primary"
                    onClick={() => void handleSave()}
                    loading={saving}
                    disabled={running}
                  >
                    保存配置
                  </Button>
                  <Button
                    icon={<ThunderboltOutlined />}
                    aria-label="立即生成"
                    onClick={() => void handleRun()}
                    loading={running}
                    disabled={saving}
                  >
                    立即生成
                  </Button>
                </div>
              </Card>
            </div>
          </div>
        </Form>
      </Spin>
    </div>
  )
}
