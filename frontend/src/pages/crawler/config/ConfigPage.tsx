import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, App, Button, Card, Descriptions, Form, InputNumber, Popconfirm, Segmented, Space, Spin, Tag, Typography } from 'antd'
import Editor, { type OnMount } from '@monaco-editor/react'
import {
  fetchConfig,
  fetchCookiesConfig,
  updateConfig,
  updateCookiesConfig,
  type AppConfig,
  type CookiesConfig,
  testCookiesConfig,
  type CookieTestResponse,
  fetchJavdbSessionStatus,
  openJavdbSession,
  closeJavdbSession,
  checkJavdbSession,
  exportJavdbSession,
  resetJavdbSession,
  type JavDBSessionStatus,
  type JavDBSessionCheck,
} from '@/api/crawler/crawlerConfig'
import { useThemeStore } from '@/stores/useThemeStore'
import styles from './ConfigPage.module.less'

const DEFAULT_COOKIE_JSON = `[
  {
    "domain": "javdb.com",
    "name": "",
    "value": "",
    "path": "/"
  }
]`

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败'
}

export default function ConfigPage() {
  const { message } = App.useApp()
  const darkMode = useThemeStore((state) => state.darkMode)
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [cookieSaving, setCookieSaving] = useState(false)
  const [cookieJson, setCookieJson] = useState('')
  const [cookieLoading, setCookieLoading] = useState(true)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [cookieTesting, setCookieTesting] = useState(false)
  const [cookieTestResult, setCookieTestResult] = useState<CookieTestResponse | null>(null)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const [sessionStatus, setSessionStatus] = useState<JavDBSessionStatus | null>(null)
  const [sessionCheck, setSessionCheck] = useState<JavDBSessionCheck | null>(null)
  const [sessionLoading, setSessionLoading] = useState(false)

  useEffect(() => {
    fetchJavdbSessionStatus()
      .then(setSessionStatus)
      .catch(() => setSessionStatus(null))
  }, [])

  useEffect(() => {
    fetchConfig()
      .then((data: AppConfig) => {
        form.setFieldsValue(data)
      })
      .catch((error: unknown) => message.error(getErrorMessage(error)))
      .finally(() => setLoading(false))
  }, [form, message])

  useEffect(() => {
    fetchCookiesConfig()
      .then((data: CookiesConfig) => {
        setCookieJson(JSON.stringify(data.cookies, null, 2))
      })
      .catch(() => {
        setCookieJson(DEFAULT_COOKIE_JSON)
      })
      .finally(() => setCookieLoading(false))
  }, [])

  const handleEditorMount: OnMount = useCallback((editor) => {
    editorRef.current = editor
  }, [])

  const validateJson = (value: string): object | null => {
    try {
      const parsed = JSON.parse(value)
      if (!Array.isArray(parsed)) {
        setJsonError('Cookie 配置必须是 JSON 数组格式')
        return null
      }
      setJsonError(null)
      return parsed
    } catch (error: unknown) {
      const msg = error instanceof SyntaxError ? error.message : '无效的 JSON 格式'
      setJsonError(msg)
      return null
    }
  }

  const handleCookieChange = (value: string | undefined) => {
    const text = value ?? ''
    setCookieJson(text)
    if (text.trim()) {
      validateJson(text)
    } else {
      setJsonError(null)
    }
  }

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

  const handleSaveCookies = async () => {
    const parsed = validateJson(cookieJson)
    if (!parsed) {
      message.error('请先修复 JSON 格式错误再保存')
      return
    }

    setCookieSaving(true)
    try {
      await updateCookiesConfig({ cookies: parsed as CookiesConfig['cookies'] })
      message.success('Cookie 配置已保存')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setCookieSaving(false)
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

  const refreshSessionStatus = async () => {
    const status = await fetchJavdbSessionStatus()
    setSessionStatus(status)
    return status
  }

  const handleOpenSession = async () => {
    setSessionLoading(true)
    try {
      const status = await openJavdbSession()
      setSessionStatus(status)
      if (status.verification_browser_open) {
        message.success('验证浏览器已打开')
      } else {
        message.warning(status.last_message)
      }
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSessionLoading(false)
    }
  }

  const handleCheckSession = async () => {
    setSessionLoading(true)
    try {
      const result = await checkJavdbSession()
      setSessionCheck(result)
      await refreshSessionStatus()
      if (result.ok) message.success(result.message)
      else message.error(result.message)
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSessionLoading(false)
    }
  }

  const handleCloseSession = async () => {
    setSessionLoading(true)
    try {
      setSessionStatus(await closeJavdbSession())
      message.success('验证浏览器已关闭')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSessionLoading(false)
    }
  }

  const handleExportSession = async () => {
    setSessionLoading(true)
    try {
      const result = await exportJavdbSession()
      message.success(`会话状态已导出: ${result.path}`)
      await refreshSessionStatus()
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSessionLoading(false)
    }
  }

  const handleResetSession = async () => {
    setSessionLoading(true)
    try {
      setSessionStatus(await resetJavdbSession())
      setSessionCheck(null)
      message.success('JavDB 会话已清除')
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setSessionLoading(false)
    }
  }

  const handleFormatJson = () => {
    try {
      const parsed = JSON.parse(cookieJson)
      const formatted = JSON.stringify(parsed, null, 2)
      setCookieJson(formatted)
      setJsonError(null)
    } catch {
      return
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
                  <InputNumber min={1} max={32} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item
                  name="DETAIL_MAX_WORKERS"
                  label="详情线程数"
                  tooltip="详情阶段并发领取 pending 子任务的线程数"
                >
                  <InputNumber min={1} max={32} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="MAX_LIST_PAGES" label="最大翻页数">
                  <InputNumber min={1} max={100} style={{ width: '100%' }} />
                </Form.Item>
              </div>
            </div>

            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>请求延迟</div>
              <div className={styles.formGrid}>
                <Form.Item name="LIST_PAGE_DELAY_MIN" label="列表页最小延迟 (秒)">
                  <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="LIST_PAGE_DELAY_MAX" label="列表页最大延迟 (秒)">
                  <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="DETAIL_PAGE_DELAY_MIN" label="详情页最小延迟 (秒)">
                  <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="DETAIL_PAGE_DELAY_MAX" label="详情页最大延迟 (秒)">
                  <InputNumber min={0} max={60} step={0.5} style={{ width: '100%' }} />
                </Form.Item>
              </div>
            </div>

            <div className={styles.formSection}>
              <div className={styles.sectionTitle}>超时与安全</div>
              <div className={styles.formGrid}>
                <Form.Item name="REQUEST_TIMEOUT" label="请求超时 (秒)">
                  <InputNumber min={5} max={120} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="SECURITY_WAIT_SECONDS" label="安全验证等待 (秒)">
                  <InputNumber min={10} max={600} style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <Form.Item
                name="JAVDB_FETCH_MODE"
                label="JavDB 请求模式"
                tooltip="静态请求速度快；浏览器模式更接近真实浏览器，适合 Cookie 有效但 static 仍返回 403 的情况"
              >
                <Segmented
                  block
                  options={[
                    { label: '静态请求', value: 'static' },
                    { label: '浏览器模式', value: 'browser' },
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
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </div>
          </Card>
        </Form>
      </div>

      <div className={styles.configRight}>
        <Card title="JavDB 访问状态" className={styles.formCard}>
          <Alert
            className={styles.cookieTestResult}
            type="info"
            showIcon
            title="普通 Chrome 是首选验证入口"
            description="如果普通 Chrome 可以通过 JavDB 验证，但 Playwright 辅助浏览器一直循环人机验证，请不要反复重试辅助浏览器。先在普通 Chrome 完成验证并导出 Cookie，再保存到 Cookie 配置中检测。"
          />
          <Space wrap className={styles.cookieActions}>
            <Button onClick={() => void handleOpenSession()} loading={sessionLoading}>
              打开辅助验证浏览器
            </Button>
            <Button onClick={() => void handleCloseSession()} loading={sessionLoading}>
              关闭验证浏览器
            </Button>
            <Button type="primary" onClick={() => void handleCheckSession()} loading={sessionLoading}>
              检测会话
            </Button>
            <Button onClick={() => void handleExportSession()} loading={sessionLoading}>
              导出会话状态
            </Button>
            <Popconfirm
              title="清除 JavDB 会话？"
              description="这会删除持久浏览器 Profile 和导出的 storage state。"
              onConfirm={() => void handleResetSession()}
            >
              <Button danger loading={sessionLoading}>
                清除失效会话
              </Button>
            </Popconfirm>
          </Space>
          <Descriptions size="small" column={1} className={styles.cookieTestResult}>
            <Descriptions.Item label="Profile">
              {sessionStatus?.profile_exists ? <Tag color="success">Profile 已创建</Tag> : <Tag>Profile 未创建</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="辅助浏览器">
              {sessionStatus?.verification_browser_open ? <Tag color="processing">已打开</Tag> : <Tag>未打开</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="运行环境">
              {sessionStatus?.runtime_environment ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="最近状态">
              {sessionCheck?.message ?? sessionStatus?.last_message ?? '尚未检测 JavDB 浏览器会话'}
            </Descriptions.Item>
          </Descriptions>
          {sessionCheck && (
            <Alert
              className={styles.cookieTestResult}
              type={sessionCheck.ok ? 'success' : 'error'}
              showIcon
              title={sessionCheck.message}
              description={`URL: ${sessionCheck.url} · 状态: ${sessionCheck.status_code ?? '-'} · 原因: ${sessionCheck.reason} · 环境: ${sessionCheck.runtime_environment}`}
            />
          )}
        </Card>
        <Card
          title="Cookie 配置"
          className={styles.formCard}
          extra={
            <div className={styles.cookieActions}>
              <Button
                onClick={() => {
                  void handleTestCookies()
                }}
                loading={cookieTesting}
              >
                测试 Cookie
              </Button>
              <Button onClick={handleFormatJson} disabled={!!jsonError && cookieJson.trim() !== ''}>
                格式化
              </Button>
              <Button
                type="primary"
                onClick={() => {
                  void handleSaveCookies()
                }}
                loading={cookieSaving}
              >
                保存 Cookie
              </Button>
            </div>
          }
        >
          {cookieLoading ? (
            <div className={styles.editorLoading}>
              <Spin />
            </div>
          ) : (
            <>
              <div className={styles.editorFrame}>
                <Editor
                  height="400px"
                  defaultLanguage="json"
                  theme={darkMode ? 'vs-dark' : 'light'}
                  value={cookieJson}
                  onChange={handleCookieChange}
                  onMount={handleEditorMount}
                  options={{
                    minimap: { enabled: false },
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    tabSize: 2,
                    formatOnPaste: true,
                  }}
                />
              </div>
              {jsonError && (
                <Typography.Text type="danger" className={styles.jsonError}>
                  JSON 格式错误: {jsonError}
                </Typography.Text>
              )}
              {cookieTestResult && (
                <Alert
                  className={styles.cookieTestResult}
                  type={cookieTestResult.ok ? 'success' : 'error'}
                  showIcon
                  title={cookieTestResult.message}
                  description={`URL: ${cookieTestResult.url} · 状态: ${cookieTestResult.status_code ?? '-'} · 原因: ${cookieTestResult.reason} · 模式: ${cookieTestResult.fetch_mode}`}
                />
              )}
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
