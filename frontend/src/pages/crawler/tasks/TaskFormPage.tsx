import { useCallback, useEffect, useMemo, useState } from 'react'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import { App, Button, Col, Form, Input, Row, Switch } from 'antd'
import {
  createCrawlTask,
  extractTaskName,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTaskCreateParams, TaskUrlEntry } from '@/api/crawlTask/types'
import { useRouteCacheControl } from '@/layout/routeCache'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import {
  detectUrlType,
  type UrlType,
} from './taskUrlUtils'
import { getRouteViewKey } from '@/routes/tags'
import UrlEntryCard from './components/UrlEntryCard'
import styles from './TaskPages.module.less'

export default function TaskFormPage() {
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [storageLocationManuallyEdited, setStorageLocationManuallyEdited] = useState(false)
  const title = useMemo(() => (isEdit ? '编辑任务' : '新建任务'), [isEdit])

  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const searchStr = useRouterState({ select: (state) => state.location.searchStr ?? '' })
  const cacheKey = getRouteViewKey(pathname, searchStr)
  const removeSelectedView = useTagsViewStore((state) => state.removeSelectedView)
  const cacheControl = useRouteCacheControl()

  const closeCurrentTag = useCallback(() => {
    const currentView = useTagsViewStore.getState().visitedViews.find((v) => v.cacheKey === cacheKey)
    if (currentView) {
      removeSelectedView(currentView)
    }
    void cacheControl.destroy(cacheKey)
  }, [cacheKey, removeSelectedView, cacheControl])

  useEffect(() => {
    if (!isEdit || !taskId) return
    form.resetFields()
    setStorageLocationManuallyEdited(false)
    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
          storage_location: task.storage_location,
          is_skip: task.is_skip,
          urls: task.urls.map((entry) => ({
            url: entry.url,
            url_type: entry.url_type,
            has_magnet: entry.has_magnet ?? true,
            has_chinese_sub: entry.has_chinese_sub ?? false,
            sort_type: entry.sort_type ?? 0,
            url_name: entry.url_name ?? '',
          })),
        })
      })
      .catch(() => message.error('任务详情加载失败'))
      .finally(() => setLoading(false))
  }, [form, isEdit, message, taskId])

  const setUrlEntryValue = useCallback(
    (index: number, patch: Partial<TaskUrlEntry>) => {
      const urls = form.getFieldValue('urls') ?? []
      form.setFieldsValue({
        urls: urls.map((entry: TaskUrlEntry, itemIndex: number) =>
          itemIndex === index ? { ...entry, ...patch } : entry,
        ),
      })
    },
    [form],
  )

  const enrichUrlEntries = useCallback(
    async (urlEntries: TaskUrlEntry[]): Promise<TaskUrlEntry[]> => {
      const enrichedEntries: TaskUrlEntry[] = []

      for (const entry of urlEntries) {
        // Auto-detect url_type if missing
        const urlType = entry.url_type || detectUrlType(entry.url) || ''

        // Auto-fetch url_name if missing
        let urlName = entry.url_name?.trim() ?? ''
        if (!urlName && entry.url && urlType) {
          try {
            const result = await extractTaskName(entry.url, urlType as UrlType)
            urlName = result.name?.trim() ?? ''
          } catch {
            urlName = ''
          }
        }

        enrichedEntries.push({
          url: entry.url,
          url_type: urlType,
          has_magnet: entry.has_magnet ?? false,
          has_chinese_sub: entry.has_chinese_sub ?? false,
          sort_type: entry.sort_type ?? 0,
          url_name: urlName,
        })
      }

      return enrichedEntries
    },
    [],
  )

  const handleSubmit = async (values: CrawlTaskCreateParams) => {
    const urlEntries = values.urls ?? []
    const urlSet = new Set<string>()
    for (const entry of urlEntries) {
      if (entry.url && urlSet.has(entry.url)) {
        message.error(`URL 重复: ${entry.url}`)
        return
      }
      if (entry.url) urlSet.add(entry.url)
    }

    setSubmitting(true)
    try {
      const enrichedEntries = await enrichUrlEntries(urlEntries)

      // Validate that all URLs have a detectable type
      for (const entry of enrichedEntries) {
        if (!entry.url_type) {
          message.error(`无法识别 URL 类型: ${entry.url}`)
          setSubmitting(false)
          return
        }
      }

      form.setFieldsValue({ urls: enrichedEntries })

      const payload: CrawlTaskCreateParams = {
        name: values.name,
        storage_location: values.storage_location,
        is_skip: values.is_skip ?? false,
        urls: enrichedEntries,
      }
      if (isEdit && taskId) {
        await updateCrawlTask(taskId, payload)
        message.success('任务已更新')
      } else {
        await createCrawlTask(payload)
        message.success('任务已创建')
      }
      closeCurrentTag()
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = useCallback(() => {
    form.resetFields()
    closeCurrentTag()
    void navigate({ to: '/crawler/tasks' })
  }, [form, navigate, closeCurrentTag])

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.subtitle}>按 URL 配置 JavDB 任务来源、筛选条件和排序规则。</p>
        </div>
      </div>

      <section className={`${styles.panel} ${styles.formPanel}`}>
        <Form<CrawlTaskCreateParams>
          form={form}
          layout="vertical"
          disabled={loading}
          onFinish={(values) => void handleSubmit(values)}
          initialValues={{
            urls: [{ has_magnet: true, has_chinese_sub: false, sort_type: 0 }],
            is_skip: false,
          }}
        >
          <Row gutter={24}>
            <Col flex="auto">
              <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
                <Input
                  placeholder="例如：某演员名称"
                  onChange={(e) => {
                    const nextValue = e.target.value
                    if (!storageLocationManuallyEdited) {
                      form.setFieldValue('storage_location', nextValue)
                    }
                  }}
                />
              </Form.Item>
            </Col>
            <Col flex="120px">
              <Form.Item name="is_skip" label="启用状态" valuePropName="checked">
                <Switch checkedChildren="禁用" unCheckedChildren="启用" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={24}>
            <Col flex="auto">
              <Form.Item
                name="storage_location"
                label="网盘路径"
                rules={[{ required: true, message: '请输入网盘路径' }]}
              >
                <Input
                  placeholder="例如：VR"
                  disabled={isEdit}
                  onChange={() => {
                    if (!isEdit) {
                      setStorageLocationManuallyEdited(true)
                    }
                  }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="URL 列表" required className={styles.urlListLabel} />

          <Form.List name="urls">
            {(fields, { add, remove }) => (
              <Row gutter={[16, 16]}>
                {fields.map((field) => (
                  <Col key={field.key} xs={24} lg={12} xl={8}>
                    <UrlEntryCard
                      index={field.name}
                      remove={fields.length > 1 ? () => remove(field.name) : undefined}
                      onNameExtracted={(index, name) => {
                        setUrlEntryValue(index, { url_name: name })
                        if (!form.getFieldValue('name')) form.setFieldsValue({ name })
                      }}
                      onUrlTypeDetected={(index, urlType) => setUrlEntryValue(index, { url_type: urlType })}
                    />
                  </Col>
                ))}
                <Col xs={24} lg={12} xl={8}>
                  <Button
                    type="dashed"
                    onClick={() => add({ has_magnet: true, has_chinese_sub: false, sort_type: 0 })}
                    icon={<PlusOutlined />}
                    className={styles.addUrlButton}
                  >
                    添加 URL
                  </Button>
                </Col>
              </Row>
            )}
          </Form.List>

          <div className={styles.actions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新' : '创建'}
            </Button>
            <Button onClick={handleCancel}>取消</Button>
          </div>
        </Form>
      </section>
    </div>
  )
}
