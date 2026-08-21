import { useEffect, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Segmented,
  Spin,
  Typography,
} from 'antd'
import {
  fetchConfig,
  updateConfig,
  type AppConfig,
  testCookiesConfig,
  type CookieTestResponse,
} from '@/api/crawler/crawlerConfig'
import { FullWidthNumberInput } from '@/components/common'
import AgentHealthCard from './components/AgentHealthCard'
import styles from './ConfigPage.module.less'

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export default function ConfigPage() {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cookieTesting, setCookieTesting] = useState(false)
  const [cookieTestResult, setCookieTestResult] = useState<CookieTestResponse | null>(null)

  useEffect(() => {
    fetchConfig()
      .then((data: AppConfig) => {
        form.setFieldsValue(data)
      })
      .catch((error: unknown) => message.error(getErrorMessage(error)))
      .finally(() => setLoading(false))
  }, [form, message])

  const handleSaveConfig = async (values: AppConfig) => {
    setSaving(true)
    try {
      await updateConfig(values)
      message.success('配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleTestCookies = async () => {
    setCookieTesting(true)
    try {
      const result = await testCookiesConfig()
      setCookieTestResult(result)
      if (result.ok) {
        message.success(result.message)
      } else {
        message.error(result.message)
      }
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setCookieTesting(false)
    }
  }

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
        <div className={styles.loadingText}>加载配置中...</div>
      </div>
    )
  }

  return (
    <div className={styles.configLayout}>
      <div className={styles.configLeft}>
        <Form form={form} layout="vertical" onFinish={handleSaveConfig}>
          <Card
            title="爬取参数"
            className={styles.formCard}
            extra={
              <Button type="primary" htmlType="submit" loading={saving}>
                保存配置
              </Button>
            }
          >
            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>并发与性能</div>
              <div className={styles.formGrid}>
                <Form.Item
                  name="LIST_MAX_WORKERS"
                  label="列表线程数"
                  tooltip="列表阶段并发处理 URL 的线程数；每个线程会顺序爬完一个 URL 的所有页"
                >
                  <FullWidthNumberInput min={1} max={32} />
                </Form.Item>
                <Form.Item
                  name="DETAIL_MAX_WORKERS"
                  label="详情线程数"
                  tooltip="详情阶段并发领取 pending 子任务的线程数"
                >
                  <FullWidthNumberInput min={1} max={32} />
                </Form.Item>
                <Form.Item name="MAX_LIST_PAGES" label="最大翻页数">
                  <FullWidthNumberInput min={1} max={100} />
                </Form.Item>
              </div>
            </div>

            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>请求延迟</div>
              <div className={styles.formGrid}>
                <Form.Item name="LIST_PAGE_DELAY_MIN" label="列表页最小延迟 (秒)">
                  <FullWidthNumberInput min={0} max={60} step={0.5} />
                </Form.Item>
                <Form.Item name="LIST_PAGE_DELAY_MAX" label="列表页最大延迟 (秒)">
                  <FullWidthNumberInput min={0} max={60} step={0.5} />
                </Form.Item>
                <Form.Item name="DETAIL_PAGE_DELAY_MIN" label="详情页最小延迟 (秒)">
                  <FullWidthNumberInput min={0} max={60} step={0.5} />
                </Form.Item>
                <Form.Item name="DETAIL_PAGE_DELAY_MAX" label="详情页最大延迟 (秒)">
                  <FullWidthNumberInput min={0} max={60} step={0.5} />
                </Form.Item>
              </div>
            </div>

            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>超时与安全</div>
              <div className={styles.formGrid}>
                <Form.Item name="REQUEST_TIMEOUT" label="请求超时 (秒)">
                  <FullWidthNumberInput min={5} max={120} />
                </Form.Item>
                <Form.Item name="SECURITY_WAIT_SECONDS" label="安全验证等待 (秒)">
                  <FullWidthNumberInput min={10} max={600} />
                </Form.Item>
                <Form.Item
                  name="AGENT_CLAIM_TIMEOUT_SECONDS"
                  label="Agent 领取超时 (秒)"
                  tooltip="Agent 在线但未领取数据库任务时的等待上限"
                >
                  <FullWidthNumberInput min={1} max={120} />
                </Form.Item>
              </div>
              <Form.Item
                name="JAVDB_FETCH_MODE"
                label="JavDB 请求模式"
                tooltip="静态请求使用后端 HTTP；Agent 模式通过 Chrome 插件采集页面片段到后端解析"
              >
                <Segmented
                  block
                  options={[
                    { label: '静态请求', value: 'static' },
                    { label: 'Chrome Agent', value: 'agent' },
                  ]}
                />
              </Form.Item>
            </div>

            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>增量策略</div>
              <Form.Item
                name="INCREMENTAL_EXIST_THRESHOLD"
                label="增量爬取阈值"
                tooltip="当某页已存在的条目数达到此阈值时，跳过后续页面。0 表示禁用（全量爬取）"
              >
                <FullWidthNumberInput min={0} />
              </Form.Item>
            </div>
          </Card>
        </Form>
      </div>

      <div className={styles.configRight}>
        <Card title="Chrome Agent" className={`${styles.formCard} ${styles.agentCard}`}>
          <AgentHealthCard />
        </Card>
      </div>

      <Card
        title="Cookie 检测"
        className={`${styles.formCard} ${styles.cookieCard}`}
        extra={
          <Button
            type="primary"
            onClick={() => {
              void handleTestCookies()
            }}
            loading={cookieTesting}
          >
            测试 Cookie
          </Button>
        }
      >
        {cookieTestResult && (
          <Alert
            className={styles.cookieTestResult}
            type={cookieTestResult.ok ? 'success' : 'error'}
            showIcon
            title={cookieTestResult.message}
            description={`URL: ${cookieTestResult.url} · 状态: ${cookieTestResult.status_code ?? '-'} · 原因: ${cookieTestResult.reason} · 模式: ${cookieTestResult.fetch_mode}`}
          />
        )}
        {!cookieTestResult && (
          <Typography.Text type="secondary">
            点击"测试 Cookie"检测当前 JavDB 访问状态。Agent 模式下 Cookie 由 Chrome 插件自动同步。
          </Typography.Text>
        )}
      </Card>
    </div>
  )
}
