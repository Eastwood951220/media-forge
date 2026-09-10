import { useMemo, useState } from 'react'
import { ArrowLeftOutlined, LinkOutlined, PlayCircleOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Avatar, Button, Empty, Modal, Radio, Select, Spin, Tag, Typography } from 'antd'
import { createTaskUrlRun } from '@/api/crawler/crawlTask'
import { fetchActress, updateActressTags } from '@/api/content/actresses'
import type { ActressExternalLink } from '@/api/content/actresses'
import { BlurredImage } from '@/components/BlurredImage'
import { queryKeys } from '@/api/queryKeys'
import styles from './ActressPages.module.less'

function formatDate(value: string | null) {
  return value || '-'
}

function formatMeasurements(actress: {
  bust_cm: number | null
  waist_cm: number | null
  hip_cm: number | null
}) {
  if (!actress.bust_cm && !actress.waist_cm && !actress.hip_cm) return '-'
  return `B${actress.bust_cm ?? '-'} / W${actress.waist_cm ?? '-'} / H${actress.hip_cm ?? '-'}`
}

function formatAge(value: string | null) {
  if (!value) return '-'
  const birthDate = new Date(`${value}T00:00:00`)
  if (Number.isNaN(birthDate.getTime())) return '-'
  const today = new Date()
  let age = today.getFullYear() - birthDate.getFullYear()
  if (
    today.getMonth() < birthDate.getMonth()
    || (today.getMonth() === birthDate.getMonth() && today.getDate() < birthDate.getDate())
  ) {
    age -= 1
  }
  return `${age}岁`
}

type CrawlMode = 'incremental' | 'full'

function formatLinkLabel(link: ActressExternalLink) {
  return `${link.label}${link.url_name ? ` · ${link.url_name}` : ''}`
}

function ActressDetailPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const params = useParams({ strict: false }) as { id: string }
  const [tagEditorOpen, setTagEditorOpen] = useState(false)
  const [tagDraft, setTagDraft] = useState<string[]>([])
  const [savingTags, setSavingTags] = useState(false)
  const [crawlOpen, setCrawlOpen] = useState(false)
  const [crawlMode, setCrawlMode] = useState<CrawlMode>('incremental')
  const [selectedLinkId, setSelectedLinkId] = useState<string>()
  const [submittingCrawl, setSubmittingCrawl] = useState(false)
  const query = useQuery({
    queryKey: queryKeys.actresses.detail(params.id),
    queryFn: () => fetchActress(params.id),
    enabled: Boolean(params.id),
  })
  const actress = query.data
  const externalLinks = actress?.external_links ?? []
  const selectedCrawlLink = useMemo(
    () => externalLinks.find((link) => link.id === selectedLinkId) ?? externalLinks[0],
    [externalLinks, selectedLinkId],
  )
  const profileFacts = actress ? [
    { label: '出道日期', value: formatDate(actress.debut_date) },
    { label: '出生日期', value: formatDate(actress.birth_date) },
    { label: '年龄', value: formatAge(actress.birth_date) },
    { label: '身高', value: actress.height_cm ? `${actress.height_cm}cm` : '-' },
    { label: '三围', value: formatMeasurements(actress) },
    { label: '罩杯', value: actress.cup || '-' },
    { label: '出生地', value: actress.birthplace || '-' },
    { label: '血型', value: actress.blood_type || '-' },
    { label: '专属厂商', value: actress.exclusive_maker || '-' },
    { label: '兴趣特长', value: actress.hobbies || '-' },
  ] : []

  const openTagEditor = () => {
    setTagDraft(actress?.tags ?? [])
    setTagEditorOpen(true)
  }

  const saveTags = async () => {
    if (!actress) return
    setSavingTags(true)
    try {
      await updateActressTags(actress.id, { tags: tagDraft })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.actresses.detail(actress.id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.actresses.all() }),
      ])
      message.success('标签已更新')
      setTagEditorOpen(false)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新标签失败')
    } finally {
      setSavingTags(false)
    }
  }

  const openCrawlModal = () => {
    if (externalLinks.length === 0) {
      message.warning('当前女优没有可爬取的关联 URL')
      return
    }
    setSelectedLinkId(externalLinks[0].id)
    setCrawlMode('incremental')
    setCrawlOpen(true)
  }

  const submitCrawl = async () => {
    if (!selectedCrawlLink) return
    setSubmittingCrawl(true)
    try {
      await createTaskUrlRun(selectedCrawlLink.task_id, {
        url_ids: [selectedCrawlLink.id],
        crawl_mode: crawlMode,
      })
      message.success('已提交影片爬取任务')
      setCrawlOpen(false)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提交爬取任务失败')
    } finally {
      setSubmittingCrawl(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.detailTopbar}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate({ to: '/content/actresses' })}>
          返回
        </Button>
      </div>

      <Spin spinning={query.isLoading}>
        {actress ? (
          <>
            <section className={styles.detailHeader}>
              <BlurredImage
                src={actress.image_url}
                alt={actress.display_name}
                className={styles.detailPortrait}
                fallback={<Avatar size={96} icon={<UserOutlined />} />}
              />
              <div className={styles.detailTitleBlock}>
                <div className={styles.detailNameRow}>
                  <div className={styles.detailNameText}>
                    <Typography.Title level={3} className={styles.detailTitle}>{actress.display_name}</Typography.Title>
                    <Typography.Text type="secondary">{actress.reading || '未记录读音'}</Typography.Text>
                  </div>
                  <div className={styles.sourceActions}>
                    <Button
                      className={styles.sourceButton}
                      icon={<PlayCircleOutlined />}
                      disabled={externalLinks.length === 0}
                      onClick={openCrawlModal}
                    >
                      爬取影片
                    </Button>
                    {actress.source_url && (
                      <Button
                        className={styles.sourceButton}
                        aria-label="查看 avjoho 资料"
                        icon={<LinkOutlined />}
                        href={actress.source_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        avjoho
                      </Button>
                    )}
                    {externalLinks.map((link) => (
                      <Button
                        key={link.id}
                        className={styles.sourceButton}
                        aria-label={`查看 ${link.label} 关联`}
                        icon={<LinkOutlined />}
                        href={link.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {link.label}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className={styles.aliasPanel}>
                  <Typography.Text className={styles.aliasLabel}>别名</Typography.Text>
                  <div className={styles.aliasList}>
                    {actress.aliases.length > 0 ? actress.aliases.map((alias) => (
                      <span key={alias} className={styles.aliasChip} title={alias}>{alias}</span>
                    )) : (
                      <Typography.Text type="secondary">-</Typography.Text>
                    )}
                  </div>
                </div>
                <div className={styles.aliasPanel}>
                  <div className={styles.tagHeader}>
                    <Typography.Text className={styles.aliasLabel}>标签</Typography.Text>
                    <Button size="small" onClick={openTagEditor}>编辑标签</Button>
                  </div>
                  <div className={styles.aliasList}>
                    {actress.tags.length > 0 ? actress.tags.map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    )) : (
                      <Typography.Text type="secondary">-</Typography.Text>
                    )}
                  </div>
                </div>
              </div>
            </section>

            <section className={styles.detailSection}>
              <Typography.Title level={4}>基础资料</Typography.Title>
              <div className={styles.factGrid}>
                {profileFacts.map((fact) => (
                  <div key={fact.label} className={styles.factItem}>
                    <Typography.Text className={styles.factLabel}>{fact.label}</Typography.Text>
                    <Typography.Text className={styles.factValue}>{fact.value}</Typography.Text>
                  </div>
                ))}
              </div>
              {actress.biography && (
                <div className={styles.biographyBox}>
                  <Typography.Text className={styles.factLabel}>简介</Typography.Text>
                  <Typography.Paragraph className={styles.biography}>{actress.biography}</Typography.Paragraph>
                </div>
              )}
            </section>

            <section className={styles.detailSection}>
              <Typography.Title level={4}>最近影片</Typography.Title>
              {actress.recent_movies.length > 0 ? (
                <div className={styles.movieGrid}>
                  {actress.recent_movies.map((movie) => (
                    <article
                      key={movie.id}
                      className={styles.movieCard}
                      role="button"
                      tabIndex={0}
                      onClick={() => navigate({ to: '/content/movies', search: { search: movie.code } })}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          navigate({ to: '/content/movies', search: { search: movie.code } })
                        }
                      }}
                    >
                      <BlurredImage
                        src={movie.cover}
                        alt={movie.title || movie.code}
                        className={styles.movieCover}
                        fallback={<VideoFallback />}
                      />
                      <div className={styles.movieBody}>
                        <Typography.Text strong className={styles.movieCode}>{movie.code}</Typography.Text>
                        <Typography.Text className={styles.movieTitle}>{movie.title}</Typography.Text>
                        <Typography.Text type="secondary">{formatDate(movie.release_date)}</Typography.Text>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <Empty description="暂无关联影片" />
              )}
            </section>

            <Modal
              title="编辑标签"
              open={tagEditorOpen}
              okText="保存"
              cancelText="取消"
              confirmLoading={savingTags}
              onOk={() => void saveTags()}
              onCancel={() => setTagEditorOpen(false)}
            >
              <Select
                mode="tags"
                allowClear
                aria-label="编辑标签"
                placeholder="输入标签"
                value={tagDraft}
                onChange={setTagDraft}
                className={styles.tagEditorSelect}
              />
            </Modal>

            <Modal
              title={`爬取 ${actress.display_name} 的影片`}
              open={crawlOpen}
              okText="开始爬取"
              cancelText="取消"
              confirmLoading={submittingCrawl}
              onOk={() => void submitCrawl()}
              onCancel={() => setCrawlOpen(false)}
            >
              <div className={styles.crawlModalBody}>
                {externalLinks.length > 1 && (
                  <Select
                    aria-label="选择爬取 URL"
                    value={selectedLinkId}
                    options={externalLinks.map((link) => ({ value: link.id, label: formatLinkLabel(link) }))}
                    onChange={setSelectedLinkId}
                  />
                )}
                {externalLinks.length === 1 && selectedCrawlLink && (
                  <Typography.Text>{formatLinkLabel(selectedCrawlLink)}</Typography.Text>
                )}
                <Radio.Group
                  aria-label="爬取模式"
                  value={crawlMode}
                  onChange={(event) => setCrawlMode(event.target.value)}
                >
                  <Radio.Button value="incremental">增量</Radio.Button>
                  <Radio.Button value="full">全量</Radio.Button>
                </Radio.Group>
              </div>
            </Modal>
          </>
        ) : (
          <Empty description={query.isError ? '女优资料加载失败' : '暂无资料'} className={styles.emptyState} />
        )}
      </Spin>
    </div>
  )
}

function VideoFallback() {
  return <div className={styles.movieFallback}>NO IMAGE</div>
}

export default ActressDetailPage
