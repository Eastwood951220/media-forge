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
  Typography,
} from 'antd'
import {
  ApiOutlined,
  ClockCircleOutlined,
  FolderOpenOutlined,
  ScanOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  getScrapingConfig,
  listMetatubeProviders,
  runScrapingScan,
  runScrapingStrm,
  updateScrapingConfig,
  type ScrapingConfig,
  type ScrapingConfigUpdate,
  type ScrapingScanSummary,
} from '@/api/scraping/scrapingConfig'
import { FullWidthNumberInput } from '@/components/common'
import DirectoryPathInput from './components/DirectoryPathInput'
import SourcePriorityList from './components/SourcePriorityList'
import { getErrorMessage, isFormValidationError } from './utils/error'
import styles from './ScrapingConfigPage.module.less'

type FormValues = {
  base_url: string
  api_key?: string
  directory_id: number
  trigger_delay_seconds: number
  scrape_root: string
  metatube_url: string
  metatube_token?: string
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
  const [sources, setSources] = useState<string[]>(['metatube:JavBus', 'metatube:FANZA'])
  const [metatubeProviders, setMetatubeProviders] = useState<string[]>([])
  const [metatubeError, setMetatubeError] = useState(false)
  const [metatubeLoading, setMetatubeLoading] = useState(false)
  const [metatubeTokenConfigured, setMetatubeTokenConfigured] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanSummary, setScanSummary] = useState<ScrapingScanSummary | null>(null)

  const applyConfig = useCallback(
    (config: ScrapingConfig) => {
      form.setFieldsValue({
        base_url: config.base_url,
        api_key: '',
        directory_id: config.directory_id ?? undefined,
        trigger_delay_seconds: config.trigger_delay_seconds,
        scrape_root: config.scrape_root,
        metatube_url: config.metatube_url,
        metatube_token: '',
      })
      setApiKeyConfigured(config.api_key_configured)
      setMaskedApiKey(config.api_key)
      setSources(config.metadata_sources ?? [])
      setMetatubeTokenConfigured(config.metatube_token_configured)
    },
    [form],
  )

  const loadProviders = useCallback(async () => {
    setMetatubeLoading(true)
    try {
      setMetatubeProviders(await listMetatubeProviders())
      setMetatubeError(false)
    } catch {
      setMetatubeError(true)
    } finally {
      setMetatubeLoading(false)
    }
  }, [])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      applyConfig(await getScrapingConfig())
      void loadProviders()
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [applyConfig, loadProviders, message])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial config load on mount is intentional.
    void loadConfig()
  }, [loadConfig])

  const buildPayload = (values: FormValues): ScrapingConfigUpdate => {
    const payload: ScrapingConfigUpdate = {
      base_url: values.base_url,
      directory_id: values.directory_id,
      trigger_delay_seconds: values.trigger_delay_seconds,
      scrape_root: values.scrape_root,
      metadata_sources: sources,
      metatube_url: values.metatube_url,
    }
    if (values.api_key?.trim()) {
      payload.api_key = values.api_key.trim()
    }
    if (values.metatube_token?.trim()) {
      payload.metatube_token = values.metatube_token.trim()
    }
    return payload
  }

  const persist = async (values: FormValues): Promise<ScrapingConfig> => {
    const updated = await updateScrapingConfig(buildPayload(values))
    applyConfig(updated)
    void loadProviders()
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

  const handleScan = async () => {
    setScanning(true)
    try {
      const summary = await runScrapingScan()
      setScanSummary(summary)
      message.success('扫描完成')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setScanning(false)
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
                    <ApiOutlined />
                    MetaTube Server
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    name="metatube_url"
                    label="MetaTube Server 地址"
                    extra="保存后读取该服务当前启用的影片来源。"
                    rules={[{ type: 'url', warningOnly: false, message: '请输入有效的服务地址' }]}
                  >
                    <Input placeholder="http://metatube-server:8080" />
                  </Form.Item>
                  <Form.Item label="MetaTube Token">
                    <Form.Item name="metatube_token" noStyle>
                      <Input.Password placeholder={metatubeTokenConfigured ? '已配置，留空保持不变' : '未启用鉴权可留空'} />
                    </Form.Item>
                  </Form.Item>
                </div>
                {metatubeError && <Alert type="warning" showIcon title="暂时无法读取 MetaTube 来源，请检查服务地址和连接。" />}
                {metatubeLoading && <Typography.Text type="secondary">正在读取 MetaTube 影片来源…</Typography.Text>}
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

              <Card
                title={
                  <span className={styles.sectionTitle}>
                    <FolderOpenOutlined />
                    刮削目录
                  </span>
                }
                className={styles.formCard}
              >
                <div className={styles.fieldGrid}>
                  <Form.Item
                    className={styles.fieldSpan2}
                    name="scrape_root"
                    label="刮削目录（本地路径）"
                    rules={[{ required: true, message: '请输入刮削目录' }]}
                    extra="文件夹列表来自服务端文件系统；Docker 部署需先把宿主机目录挂载到容器。"
                  >
                    <DirectoryPathInput placeholder="/mnt/cd2/media" />
                  </Form.Item>
                </div>
                <div className={styles.fieldGrid}>
                  <Form.Item label="元数据源优先级" className={styles.fieldSpan2}>
                    <SourcePriorityList
                      sources={sources}
                      availableSources={metatubeProviders.map((name) => `metatube:${name}`)}
                      labels={{
                        ...Object.fromEntries(metatubeProviders.map((name) => [`metatube:${name}`, `${name}（MetaTube）`])),
                      }}
                      onChange={setSources}
                    />
                  </Form.Item>
                </div>
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
                    disabled={saving || scanning}
                  >
                    立即生成
                  </Button>
                  <Button
                    icon={<ScanOutlined />}
                    aria-label="扫描目录"
                    onClick={() => void handleScan()}
                    loading={scanning}
                    disabled={saving || running}
                  >
                    扫描目录
                  </Button>
                  {scanSummary && (
                    <Alert
                      type="success"
                      showIcon
                      title={(
                        <span>
                          扫描 {scanSummary.folders_scanned} 个文件夹，已刮削 {scanSummary.scraped_folders}，
                          未刮削 {scanSummary.not_scraped_folders}，匹配 {scanSummary.matched_movies} 部电影
                        </span>
                      )}
                    />
                  )}
                </div>
              </Card>
            </div>
          </div>
        </Form>
      </Spin>
    </div>
  )
}
