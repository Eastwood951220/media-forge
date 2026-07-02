import { useCallback, useEffect, useMemo, useState } from 'react'
import { MinusCircleOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { App, Button, Card, Col, Form, Input, Row, Select, Switch } from 'antd'
import {
  createCrawlTask,
  extractTaskName,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawlTask'
import type { CrawlTaskCreateParams, TaskUrlEntry } from '@/api/crawlTask/types'
import {
  buildFinalUrlPreview,
  detectUrlType,
  SEARCH_SORT_OPTIONS,
  SORT_OPTIONS,
  type UrlType,
  URL_TYPE_LABELS,
} from './taskUrlUtils'
import styles from './TaskPages.module.less'

function UrlEntryCard({
  index,
  remove,
  onNameExtracted,
  onUrlTypeDetected,
}: {
  index: number
  remove?: () => void
  onNameExtracted: (index: number, name: string) => void
  onUrlTypeDetected: (index: number, urlType: UrlType) => void
}) {
  const { message } = App.useApp()
  const [extracting, setExtracting] = useState(false)

  return (
    <Card
      size="small"
      title={`URL ${index + 1}`}
      className={styles.urlCard}
      extra={
        remove ? (
          <Button type="text" danger icon={<MinusCircleOutlined />} onClick={remove} size="small" />
        ) : null
      }
    >
      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url !== cur.urls?.[index]?.url}>
        {({ getFieldValue }) => {
          const url = getFieldValue(['urls', index, 'url']) as string
          const detected = url ? detectUrlType(url) : null
          const currentType = getFieldValue(['urls', index, 'url_type']) as UrlType | undefined

          if (detected && detected !== currentType) {
            window.setTimeout(() => onUrlTypeDetected(index, detected), 0)
          }

          return (
            <>
              <Form.Item name={[index, 'url']} label="URL" rules={[{ required: true, message: '请输入 URL' }]}>
                <Input placeholder="https://javdb.com/actors/..." />
              </Form.Item>
              <Form.Item label="URL 类型">
                <Input value={detected ? URL_TYPE_LABELS[detected] : url ? '无法识别' : '请输入 URL'} disabled />
              </Form.Item>
              <Form.Item name={[index, 'url_type']} hidden>
                <Input />
              </Form.Item>
              <Form.Item name={[index, 'url_name']} hidden>
                <Input />
              </Form.Item>
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_type !== cur.urls?.[index]?.url_type}>
        {({ getFieldValue }) => {
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          if (!urlType) return null
          const sortOptions = urlType === 'search' ? SEARCH_SORT_OPTIONS : SORT_OPTIONS
          const showSort = urlType === 'video_codes' || urlType === 'search'
          return (
            <>
              <Form.Item name={[index, 'has_magnet']} label="含磁力链接" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={[index, 'has_chinese_sub']} label="含中文字幕" valuePropName="checked">
                <Switch />
              </Form.Item>
              {showSort ? (
                <Form.Item name={[index, 'sort_type']} label="排序方式">
                  <Select options={sortOptions} />
                </Form.Item>
              ) : null}
            </>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const baseUrl = (getFieldValue(['urls', index, 'url']) as string) ?? ''
          const urlType = getFieldValue(['urls', index, 'url_type']) as UrlType
          const hasMagnet = (getFieldValue(['urls', index, 'has_magnet']) as boolean) ?? false
          const hasSub = (getFieldValue(['urls', index, 'has_chinese_sub']) as boolean) ?? false
          const sortType = (getFieldValue(['urls', index, 'sort_type']) as number) ?? 0
          const finalUrl = urlType ? buildFinalUrlPreview(baseUrl, urlType, hasMagnet, hasSub, sortType) : baseUrl
          return (
            <Form.Item label="最终 URL 预览">
              <Input value={finalUrl} disabled />
            </Form.Item>
          )
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.urls?.[index]?.url_name !== cur.urls?.[index]?.url_name}>
        {({ getFieldValue }) => {
          const urlName = getFieldValue(['urls', index, 'url_name']) as string | undefined
          return urlName ? (
            <Form.Item label="URL 名称">
              <Input value={urlName} disabled />
            </Form.Item>
          ) : null
        }}
      </Form.Item>

      <Form.Item noStyle shouldUpdate>
        {({ getFieldValue }) => {
          const url = getFieldValue(['urls', index, 'url']) as string
          const urlType = getFieldValue(['urls', index, 'url_type']) as string
          return (
            <Button
              icon={<SearchOutlined />}
              loading={extracting}
              disabled={!url || !urlType}
              onClick={async () => {
                setExtracting(true)
                try {
                  const result = await extractTaskName(url, urlType)
                  if (result.name) onNameExtracted(index, result.name)
                  else message.warning('未能提取到名称')
                } finally {
                  setExtracting(false)
                }
              }}
            >
              获取名称
            </Button>
          )
        }}
      </Form.Item>
    </Card>
  )
}

export default function TaskFormPage() {
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const title = useMemo(() => (isEdit ? '编辑任务' : '新建任务'), [isEdit])

  useEffect(() => {
    if (!isEdit || !taskId) return
    setLoading(true)
    getCrawlTask(taskId)
      .then((task) => {
        form.setFieldsValue({
          name: task.name,
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

  const enrichUrlEntriesWithNames = useCallback(
    async (urlEntries: TaskUrlEntry[]): Promise<TaskUrlEntry[]> => {
      const enrichedEntries: TaskUrlEntry[] = []

      for (const entry of urlEntries) {
        let urlName = entry.url_name?.trim() ?? ''

        if (!urlName && entry.url && entry.url_type) {
          try {
            const result = await extractTaskName(entry.url, entry.url_type)
            urlName = result.name?.trim() ?? ''
          } catch {
            urlName = ''
          }
        }

        enrichedEntries.push({
          url: entry.url,
          url_type: entry.url_type,
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
      const enrichedEntries = await enrichUrlEntriesWithNames(urlEntries)
      form.setFieldsValue({ urls: enrichedEntries })

      const payload: CrawlTaskCreateParams = {
        name: values.name,
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
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

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
                <Input placeholder="例如：某演员名称" />
              </Form.Item>
            </Col>
            <Col flex="120px">
              <Form.Item name="is_skip" label="启用状态" valuePropName="checked">
                <Switch checkedChildren="禁用" unCheckedChildren="启用" />
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
            <Button onClick={() => navigate({ to: '/crawler/tasks' })}>取消</Button>
          </div>
        </Form>
      </section>
    </div>
  )
}
