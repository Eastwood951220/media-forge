import { useCallback, useState } from 'react'
import Editor from '@monaco-editor/react'
import { Alert, App, Button, Drawer, Space, Typography } from 'antd'
import {
  fetchCookiesConfig,
  updateCookiesConfig,
  testCookiesConfig,
  type CookieTestResponse,
  type CookiesConfig,
} from '@/api/crawler/crawlerConfig'
import { requestAgentCookieSync, type AgentCookieSyncResponse } from '@/api/crawler/crawlerAgent'
import styles from '../ConfigPage.module.less'

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

function parseCookieJson(text: string): CookiesConfig['cookies'] {
  const parsed = JSON.parse(text)
  if (!Array.isArray(parsed)) {
    throw new Error('Cookie 配置必须是 JSON 数组格式')
  }
  return parsed as CookiesConfig['cookies']
}

export interface CookieConfigDrawerProps {
  open: boolean
  onClose: () => void
}

export default function CookieConfigDrawer({ open, onClose }: CookieConfigDrawerProps) {
  const { message } = App.useApp()
  const [cookieJson, setCookieJson] = useState(DEFAULT_COOKIE_JSON)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testing, setTesting] = useState(false)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [syncResult, setSyncResult] = useState<AgentCookieSyncResponse | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<CookieTestResponse | null>(null)

  const loadCookies = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchCookiesConfig()
      const cookies = data.cookies.length ? data.cookies : JSON.parse(DEFAULT_COOKIE_JSON)
      setCookieJson(JSON.stringify(cookies, null, 2))
      setJsonError(null)
    } catch {
      setCookieJson(DEFAULT_COOKIE_JSON)
      setJsonError(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleAfterOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen) return
    setSyncResult(null)
    setSyncError(null)
    setTestResult(null)
    void loadCookies()
  }, [loadCookies])

  const handleCookieChange = (value: string | undefined) => {
    const text = value ?? ''
    setCookieJson(text)
    if (!text.trim()) {
      setJsonError(null)
      return
    }
    try {
      parseCookieJson(text)
      setJsonError(null)
    } catch (error) {
      setJsonError(getErrorMessage(error))
    }
  }

  const handleFormat = () => {
    try {
      setCookieJson(JSON.stringify(parseCookieJson(cookieJson), null, 2))
      setJsonError(null)
    } catch (error) {
      setJsonError(getErrorMessage(error))
    }
  }

  const handleSave = async () => {
    let cookies: CookiesConfig['cookies']
    try {
      cookies = parseCookieJson(cookieJson)
      setJsonError(null)
    } catch (error) {
      setJsonError(getErrorMessage(error))
      return
    }
    setSaving(true)
    try {
      await updateCookiesConfig({ cookies })
      message.success('Cookie 配置已保存')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const handleAgentSync = async () => {
    setSyncing(true)
    setSyncError(null)
    try {
      const result = await requestAgentCookieSync()
      setSyncResult(result)
      await loadCookies()
      message.success('Chrome Agent Cookie 已同步')
    } catch (error) {
      setSyncError(getErrorMessage(error))
    } finally {
      setSyncing(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    try {
      const result = await testCookiesConfig()
      setTestResult(result)
      if (result.ok) {
        message.success('Cookie 检测完成')
      } else {
        message.error(result.message)
      }
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setTesting(false)
    }
  }

  return (
    <Drawer
      title="Cookie 检测"
      open={open}
      onClose={onClose}
      afterOpenChange={handleAfterOpenChange}
      size={720}
      className={styles.cookieDrawer}
      footer={
        <div className={styles.cookieDrawerFooter}>
          <Button onClick={onClose}>关闭</Button>
          <Space wrap>
            <Button onClick={handleFormat} disabled={loading}>
              格式化
            </Button>
            <Button onClick={() => void handleAgentSync()} loading={syncing} disabled={loading}>
              从 Chrome Agent 获取
            </Button>
            <Button onClick={() => void handleTest()} loading={testing}>
              测试 Cookie
            </Button>
            <Button type="primary" onClick={() => void handleSave()} loading={saving} disabled={loading}>
              保存 Cookie
            </Button>
          </Space>
        </div>
      }
    >
      <div className={styles.editorFrame}>
        <Editor
          height="100%"
          defaultLanguage="json"
          value={cookieJson}
          loading="加载 Cookie 中..."
          onChange={handleCookieChange}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            tabSize: 2,
            formatOnPaste: true,
            readOnly: loading,
          }}
        />
      </div>
      {jsonError && (
        <Typography.Text className={styles.jsonError} type="danger">
          JSON 格式错误: {jsonError}
        </Typography.Text>
      )}
      {syncError && (
        <Alert className={styles.cookieTestResult} type="error" showIcon title={syncError} />
      )}
      {syncResult && (
        <Alert
          className={styles.cookieTestResult}
          type={syncResult.accepted > 0 ? 'success' : 'warning'}
          showIcon
          title={`已获取 ${syncResult.accepted} 个 Cookie`}
          description={`拒绝: ${syncResult.rejected} · 名称: ${syncResult.cookie_names.join(', ') || '-'}`}
        />
      )}
      {testResult && (
        <Alert
          className={styles.cookieTestResult}
          type={testResult.ok ? 'success' : 'error'}
          showIcon
          title={testResult.message}
          description={`URL: ${testResult.url} · 状态: ${testResult.status_code ?? '-'} · 原因: ${testResult.reason} · 模式: ${testResult.fetch_mode}`}
        />
      )}
    </Drawer>
  )
}
