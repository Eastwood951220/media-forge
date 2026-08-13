import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { DeleteOutlined, EditOutlined, PlusOutlined, UnorderedListOutlined, AppstoreOutlined } from '@ant-design/icons'
import { useNavigate, useParams, useRouterState } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { App, Button, Col, Form, Input, Row, Space, Switch, Table, Tooltip, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createCrawlTask,
  extractTaskName,
  getCrawlTask,
  updateCrawlTask,
} from '@/api/crawler/crawlTask'
import type { CrawlTaskCreateParams, TaskUrlEntry } from '@/api/crawler/crawlTask/types'
import { useRouteCacheControl } from '@/layout/routeCache'
import { invalidateCrawlerTaskLists } from '@/api/queryInvalidation'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import {
  buildFinalUrlPreview,
  detectUrlSource,
  detectUrlType,
  type UrlType,
  URL_TYPE_LABELS,
} from './taskUrlUtils'
import { getRouteViewKey } from '@/routes/tags'
import UrlEntryCard from './components/UrlEntryCard'
import UrlEntryDrawer from './components/UrlEntryDrawer'
import styles from './TaskPages.module.less'

const COMPACT_PAGE_SIZE = 10

type UrlDrawerState =
  | { open: false; mode: 'create'; index: null }
  | { open: true; mode: 'create'; index: null }
  | { open: true; mode: 'edit'; index: number; initialValue: TaskUrlEntry }

function normalizeUrlEntriesForSubmit(entries: TaskUrlEntry[] | undefined): TaskUrlEntry[] {
  return (entries ?? [])
    .filter((entry) => Boolean(entry?.url?.trim()))
    .map((entry) => ({
      id: entry.id,
      position: entry.position,
      url: entry.url.trim(),
      url_type: entry.url_type,
      has_magnet: entry.has_magnet ?? false,
      has_chinese_sub: entry.has_chinese_sub ?? false,
      sort_type: entry.sort_type ?? 0,
      source: entry.source,
      final_url: entry.final_url,
      url_name: entry.url_name?.trim() ?? '',
    }))
}

export default function TaskFormPage() {
  const params = useParams({ strict: false }) as { id?: string }
  const taskId = params.id
  const isEdit = Boolean(taskId)
  const navigate = useNavigate()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<CrawlTaskCreateParams>()
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [storageLocationManuallyEdited, setStorageLocationManuallyEdited] = useState(false)
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card')
  const [currentPage, setCurrentPage] = useState(1)
  const [urlDrawer, setUrlDrawer] = useState<UrlDrawerState>({
    open: false,
    mode: 'create',
    index: null,
  })
  const formListAddRef = useRef<((entry: TaskUrlEntry) => void) | null>(null)
  const formListUrlCountRef = useRef(0)
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
            id: entry.id,
            position: entry.position,
            url: entry.url,
            url_type: entry.url_type,
            has_magnet: entry.has_magnet ?? true,
            has_chinese_sub: entry.has_chinese_sub ?? false,
            sort_type: entry.sort_type ?? 0,
            source: entry.source,
            final_url: entry.final_url,
            url_name: entry.url_name ?? '',
          })),
        })
        // Auto-switch to table view when many URLs
        if (task.urls.length > 6) {
          setViewMode('table')
        }
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
        // Auto-detect url_type if missing; for JavBus URLs default to 'detail'
        const source = detectUrlSource(entry.url)
        const urlType = entry.url_type || detectUrlType(entry.url) || (source === 'javbus' ? 'detail' : '')

        // Auto-fetch url_name if missing
        let urlName = entry.url_name?.trim() ?? ''
        if (!urlName && entry.url && (urlType || source)) {
          try {
            const result = await extractTaskName(entry.url, (urlType || 'detail') as UrlType)
            urlName = result.name?.trim() ?? ''
          } catch {
            urlName = ''
          }
        }

        enrichedEntries.push({
          id: entry.id,
          position: entry.position,
          url: entry.url.trim(),
          url_type: urlType,
          has_magnet: entry.has_magnet ?? false,
          has_chinese_sub: entry.has_chinese_sub ?? false,
          sort_type: entry.sort_type ?? 0,
          source: entry.source,
          final_url: entry.final_url,
          url_name: urlName,
        })
      }

      return enrichedEntries
    },
    [],
  )

  const handleSubmit = async (values: CrawlTaskCreateParams) => {
    const currentUrlEntries = form.getFieldValue('urls') as TaskUrlEntry[] | undefined
    const urlEntries = normalizeUrlEntriesForSubmit(currentUrlEntries)

    if (urlEntries.length === 0) {
      message.error('请至少保留一个 URL')
      return
    }

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

      // Validate that all URLs have a detectable type or source
      for (const entry of enrichedEntries) {
        const source = detectUrlSource(entry.url)
        if (!entry.url_type && !source) {
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
      await invalidateCrawlerTaskLists(queryClient)
      void navigate({ to: '/crawler/tasks' })
    } finally {
      setSubmitting(false)
    }
  }

  const getUrlEntryAt = useCallback((index: number): TaskUrlEntry => {
    const urls = form.getFieldValue('urls') ?? []
    return urls[index] ?? { url: '', url_type: '', has_magnet: true, has_chinese_sub: false, sort_type: 0, url_name: '' }
  }, [form])

  const openCreateUrlDrawer = useCallback(() => {
    setUrlDrawer({ open: true, mode: 'create', index: null })
  }, [])

  const openEditUrlDrawer = useCallback((index: number) => {
    setUrlDrawer({ open: true, mode: 'edit', index, initialValue: getUrlEntryAt(index) })
  }, [getUrlEntryAt])

  const closeUrlDrawer = useCallback(() => {
    setUrlDrawer({ open: false, mode: 'create', index: null })
  }, [])

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
          <p className={styles.subtitle}>按 URL 配置 JavDB/JavBus 任务来源、筛选条件和排序规则。</p>
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

          <div className={styles.urlListHeader}>
            <Form.Item label="URL 列表" required className={styles.urlListLabel} />
            <Space>
              <Button
                type={viewMode === 'card' ? 'primary' : 'default'}
                icon={<AppstoreOutlined />}
                onClick={() => setViewMode('card')}
                size="small"
              >
                卡片
              </Button>
              <Button
                type={viewMode === 'table' ? 'primary' : 'default'}
                icon={<UnorderedListOutlined />}
                onClick={() => setViewMode('table')}
                size="small"
              >
                列表
              </Button>
            </Space>
          </div>

          <Form.List name="urls">
            {(fields, { add, remove }) => {
              const urlCount = fields.length
              formListAddRef.current = add
              formListUrlCountRef.current = urlCount

              if (viewMode === 'table') {
                const tableData = fields.map((field) => ({
                  key: field.key,
                  index: field.name,
                  form,
                }))

                const columns: ColumnsType<typeof tableData[0]> = [
                  {
                    title: '#',
                    width: 56,
                    render: (_, __, i) => (currentPage - 1) * COMPACT_PAGE_SIZE + i + 1,
                  },
                  {
                    title: 'URL',
                    dataIndex: 'index',
                    ellipsis: true,
                    render: (index: number) => {
                      const currentUrl = form.getFieldValue(['urls', index, 'url']) as string ?? '-'
                      return (
                        <Tooltip title={currentUrl}>
                          <span className={styles.tableUrlCell}>{currentUrl}</span>
                        </Tooltip>
                      )
                    },
                  },
                  {
                    title: '类型',
                    width: 150,
                    render: (_, record) => {
                      const currentUrl = form.getFieldValue(['urls', record.index, 'url']) as string ?? ''
                      const source = currentUrl ? detectUrlSource(currentUrl) : null
                      const urlType = form.getFieldValue(['urls', record.index, 'url_type']) as UrlType
                      const sourceLabel = source === 'javbus' ? 'JavBus' : source === 'javdb' ? 'JavDB' : null
                      const typeLabel = sourceLabel && urlType && URL_TYPE_LABELS[urlType]
                        ? `${sourceLabel} - ${URL_TYPE_LABELS[urlType]}`
                        : sourceLabel || (urlType ? URL_TYPE_LABELS[urlType] ?? urlType : '-')
                      return typeLabel !== '-' ? <Tag>{typeLabel}</Tag> : '-'
                    },
                  },
                  {
                    title: '名称',
                    width: 220,
                    ellipsis: true,
                    render: (_, record) => {
                      const urlName = form.getFieldValue(['urls', record.index, 'url_name']) as string ?? '-'
                      return (
                        <Tooltip title={urlName}>
                          <span className={styles.tableUrlCell}>{urlName}</span>
                        </Tooltip>
                      )
                    },
                  },
                  {
                    title: '最终 URL',
                    ellipsis: true,
                    render: (_, record) => {
                      const baseUrl = form.getFieldValue(['urls', record.index, 'url']) as string ?? ''
                      const source = baseUrl ? detectUrlSource(baseUrl) : null
                      const urlType = form.getFieldValue(['urls', record.index, 'url_type']) as UrlType
                      const hasMagnet = form.getFieldValue(['urls', record.index, 'has_magnet']) as boolean ?? false
                      const hasSub = form.getFieldValue(['urls', record.index, 'has_chinese_sub']) as boolean ?? false
                      const sortType = form.getFieldValue(['urls', record.index, 'sort_type']) as number ?? 0
                      const finalUrl = urlType ? buildFinalUrlPreview(baseUrl, urlType, hasMagnet, hasSub, sortType, source) : baseUrl
                      return (
                        <Tooltip title={finalUrl}>
                          <span className={styles.tableUrlCell}>{finalUrl}</span>
                        </Tooltip>
                      )
                    },
                  },
                  {
                    title: '操作',
                    width: 104,
                    align: 'right' as const,
                    render: (_, record) => (
                      <span className={styles.urlTableActions}>
                        <Tooltip title="编辑">
                          <Button
                            aria-label={`编辑 URL ${record.index + 1}`}
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => openEditUrlDrawer(record.index)}
                          />
                        </Tooltip>
                        <Tooltip title={fields.length > 1 ? '删除' : '至少保留一个 URL'}>
                          <Button
                            aria-label={`删除 URL ${record.index + 1}`}
                            type="text"
                            size="small"
                            danger
                            disabled={fields.length <= 1}
                            icon={<DeleteOutlined />}
                            onClick={() => remove(record.index)}
                          />
                        </Tooltip>
                      </span>
                    ),
                  },
                ]

                return (
                  <div className={styles.urlTableContainer}>
                    <div className={styles.urlTableToolbar}>
                      <span className={styles.urlCount}>共 {urlCount} 个 URL</span>
                      <Button
                        type="dashed"
                        onClick={openCreateUrlDrawer}
                        icon={<PlusOutlined />}
                        size="small"
                      >
                        添加 URL
                      </Button>
                    </div>
                    <Table
                      columns={columns}
                      dataSource={tableData}
                      pagination={{
                        current: currentPage,
                        pageSize: COMPACT_PAGE_SIZE,
                        total: urlCount,
                        onChange: setCurrentPage,
                        showTotal: (total) => `共 ${total} 条`,
                        size: 'small',
                      }}
                      size="small"
                      scroll={{ x: 1080 }}
                    />
                  </div>
                )
              }

              // Card view
              return (
                <Row gutter={[16, 16]}>
                  {fields.map((field) => (
                    <Col key={field.key} xs={24} lg={12} xl={8} data-url-index={field.name}>
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
              )
            }}
          </Form.List>

          <div className={styles.actions}>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {isEdit ? '更新' : '创建'}
            </Button>
            <Button onClick={handleCancel}>取消</Button>
          </div>
        </Form>
        <UrlEntryDrawer
          open={urlDrawer.open}
          mode={urlDrawer.mode}
          initialValue={urlDrawer.mode === 'edit' ? urlDrawer.initialValue : undefined}
          onCancel={closeUrlDrawer}
          onSave={({ entry, extractedName }) => {
            if (urlDrawer.mode === 'edit' && urlDrawer.index !== null) {
              const urls = form.getFieldValue('urls') ?? []
              form.setFieldsValue({
                urls: urls.map((item: TaskUrlEntry, i: number) =>
                  i === urlDrawer.index ? entry : item,
                ),
              })
            } else {
              formListAddRef.current?.(entry)
              setCurrentPage(Math.max(1, Math.ceil((formListUrlCountRef.current + 1) / COMPACT_PAGE_SIZE)))
            }
            if (extractedName && !form.getFieldValue('name')) {
              form.setFieldValue('name', extractedName)
              if (!storageLocationManuallyEdited) form.setFieldValue('storage_location', extractedName)
            }
            closeUrlDrawer()
          }}
        />
      </section>
    </div>
  )
}
