import {useCallback, useEffect, useRef, useState} from 'react'
import {App, Button, Card, Form, InputNumber, Typography} from 'antd'
import Editor, {type OnMount} from '@monaco-editor/react'
import {
    fetchConfig,
    fetchCookiesConfig,
    updateConfig,
    updateCookiesConfig,
    type AppConfig,
    type CookiesConfig,
} from '@/api/crawler/crawlerConfig'
import {useThemeStore} from '@/stores/useThemeStore'
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
    const {message} = App.useApp()
    const darkMode = useThemeStore((state) => state.darkMode)
    const [form] = Form.useForm()
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [cookieSaving, setCookieSaving] = useState(false)
    const [cookieJson, setCookieJson] = useState('')
    const [cookieLoading, setCookieLoading] = useState(true)
    const [jsonError, setJsonError] = useState<string | null>(null)
    const editorRef = useRef<Parameters<OnMount>[0] | null>(null)

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
            await updateCookiesConfig({cookies: parsed as CookiesConfig['cookies']})
            message.success('Cookie 配置已保存')
        } catch (error: unknown) {
            message.error(getErrorMessage(error))
        } finally {
            setCookieSaving(false)
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

    if (loading) return null

    return (
        <div className={styles.configLayout}>
            <div className={styles.configLeft}>
                <Form form={form} layout="vertical" onFinish={handleSaveConfig}>
                    <Card title="爬取参数" className={styles.formCard}
                          extra={
                              <Button type="primary" htmlType="submit" loading={saving}>
                                  保存配置
                              </Button>
                          }>
                        <Form.Item name="MAX_LIST_PAGES" label="最大翻页数">
                            <InputNumber min={1} max={100} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="LIST_PAGE_DELAY_MIN" label="列表页最小延迟 (秒)">
                            <InputNumber min={0} max={60} step={0.5} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="LIST_PAGE_DELAY_MAX" label="列表页最大延迟 (秒)">
                            <InputNumber min={0} max={60} step={0.5} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="DETAIL_PAGE_DELAY_MIN" label="详情页最小延迟 (秒)">
                            <InputNumber min={0} max={60} step={0.5} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="DETAIL_PAGE_DELAY_MAX" label="详情页最大延迟 (秒)">
                            <InputNumber min={0} max={60} step={0.5} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="SECURITY_WAIT_SECONDS" label="安全验证等待 (秒)">
                            <InputNumber min={10} max={600} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item name="REQUEST_TIMEOUT" label="请求超时 (秒)">
                            <InputNumber min={5} max={120} style={{width: '100%'}}/>
                        </Form.Item>
                        <Form.Item
                            name="INCREMENTAL_EXIST_THRESHOLD"
                            label="增量爬取阈值"
                            tooltip="当某页已存在的条目数达到此阈值时，跳过后续页面。0 表示禁用（全量爬取）"
                        >
                            <InputNumber min={0} style={{width: '100%'}}/>
                        </Form.Item>
                    </Card>
                </Form>
            </div>

            <div className={styles.configRight}>
                <Card
                    title="Cookie 配置"
                    className={styles.formCard}
                    extra={
                        <div className={styles.cookieActions}>
                            <Button onClick={handleFormatJson} disabled={!!jsonError && cookieJson.trim() !== ''}>
                                格式化
                            </Button>
                            <Button type="primary" onClick={() => {
                                void handleSaveCookies()
                            }} loading={cookieSaving}>
                                保存 Cookie
                            </Button>
                        </div>
                    }
                >
                    {cookieLoading ? null : (
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
                                        minimap: {enabled: false},
                                        lineNumbers: 'on',
                                        scrollBeyondLastLine: false,
                                        wordWrap: 'on',
                                        tabSize: 2,
                                        formatOnPaste: true,
                                    }}
                                />
                            </div>
                            {jsonError && (
                                <Typography.Text type="danger" style={{display: 'block', marginTop: 8}}>
                                    JSON 格式错误: {jsonError}
                                </Typography.Text>
                            )}
                        </>
                    )}
                </Card>
            </div>
        </div>
    )
}
