import { useMemo, useState } from 'react'
import { FilterOutlined, PlayCircleOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { App, Avatar, Button, Card, Empty, Input, Modal, Pagination, Radio, Select, Spin, Tag, Typography } from 'antd'
import { createTaskUrlRun } from '@/api/crawler/crawlTask'
import { fetchActresses, getActressTags } from '@/api/content/actresses'
import type { ActressExternalLink, ActressProfile } from '@/api/content/actresses'
import { BlurredImage } from '@/components/BlurredImage'
import { queryKeys } from '@/api/queryKeys'
import styles from './ActressPages.module.less'

const PAGE_SIZE_OPTIONS = ['8', '16', '24', '40']
const CUP_OPTIONS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'T']
  .map((value) => ({ value, label: `${value}杯` }))
const HEIGHT_OPTIONS = [
  { value: '149_under', label: '149cm以下' },
  { value: '150_153', label: '150-153cm' },
  { value: '154_157', label: '154-157cm' },
  { value: '158_161', label: '158-161cm' },
  { value: '162_165', label: '162-165cm' },
  { value: '166_169', label: '166-169cm' },
  { value: '170_over', label: '170cm以上' },
]
const AGE_OPTIONS = [
  { value: '20_under', label: '20代以下' },
  { value: '30s', label: '30代' },
  { value: '40s', label: '40代' },
  { value: '50s', label: '50代' },
  { value: '60s', label: '60代' },
  { value: '70s', label: '70代' },
  { value: '80s', label: '80代' },
]
const BUST_OPTIONS = [
  { value: '79_under', label: 'B79cm以下' },
  { value: '80_84', label: 'B80-84cm' },
  { value: '85_89', label: 'B85-89cm' },
  { value: '90_94', label: 'B90-94cm' },
  { value: '95_99', label: 'B95-99cm' },
  { value: '100_over', label: 'B100cm以上' },
]
const WAIST_OPTIONS = [
  { value: '55_under', label: 'W55cm以下' },
  { value: '56_59', label: 'W56-59cm' },
  { value: '60_63', label: 'W60-63cm' },
  { value: '64_67', label: 'W64-67cm' },
  { value: '68_69', label: 'W68-69cm' },
  { value: '70_over', label: 'W70cm以上' },
]
const HIP_OPTIONS = [
  { value: '80_under', label: 'H80cm以下' },
  { value: '81_84', label: 'H81-84cm' },
  { value: '85_88', label: 'H85-88cm' },
  { value: '89_92', label: 'H89-92cm' },
  { value: '93_95', label: 'H93-95cm' },
  { value: '96_over', label: 'H96cm以上' },
]

type CrawlMode = 'incremental' | 'full'

function formatLinkLabel(link: ActressExternalLink) {
  return `${link.label}${link.url_name ? ` · ${link.url_name}` : ''}`
}

function ActressCard({
  actress,
  onCrawl,
  onOpen,
}: {
  actress: ActressProfile
  onCrawl: (actress: ActressProfile) => void
  onOpen: (actress: ActressProfile) => void
}) {
  const visibleTags = actress.tags.slice(0, 3)
  const hiddenTagCount = Math.max(0, actress.tags.length - visibleTags.length)

  return (
    <Card
      hoverable
      className={styles.actressCard}
      cover={
        <BlurredImage
          src={actress.image_url}
          alt={actress.display_name}
          className={styles.actressCover}
          fallback={<Avatar size={72} icon={<UserOutlined />} />}
          preview={false}
          stopPropagation={false}
        />
      }
      onClick={() => onOpen(actress)}
    >
      <Typography.Title level={5} className={styles.actressName}>
        {actress.display_name}
      </Typography.Title>
      <Typography.Text type="secondary" className={styles.actressReading}>
        {actress.reading || actress.aliases[0] || '未记录读音'}
      </Typography.Text>
      <div className={styles.cardTags}>
        {visibleTags.map((tag) => (
          <Tag key={tag}>{tag}</Tag>
        ))}
        {hiddenTagCount > 0 && <Tag>+{hiddenTagCount}</Tag>}
      </div>
      <Button
        block
        className={styles.cardAction}
        icon={<PlayCircleOutlined />}
        disabled={(actress.external_links ?? []).length === 0}
        onClick={(event) => {
          event.stopPropagation()
          onCrawl(actress)
        }}
      >
        爬取影片
      </Button>
    </Card>
  )
}

function ActressListPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState<8 | 16 | 24 | 40>(24)
  const [keyword, setKeyword] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [cup, setCup] = useState<string | undefined>()
  const [heightRange, setHeightRange] = useState<string | undefined>()
  const [ageRange, setAgeRange] = useState<string | undefined>()
  const [bustRange, setBustRange] = useState<string | undefined>()
  const [waistRange, setWaistRange] = useState<string | undefined>()
  const [hipRange, setHipRange] = useState<string | undefined>()
  const [tagFilters, setTagFilters] = useState<string[]>([])
  const [crawlTarget, setCrawlTarget] = useState<ActressProfile | null>(null)
  const [crawlMode, setCrawlMode] = useState<CrawlMode>('incremental')
  const [selectedLinkId, setSelectedLinkId] = useState<string>()
  const [submittingCrawl, setSubmittingCrawl] = useState(false)
  const params = useMemo(() => ({
    page,
    limit,
    keyword: keyword.trim() || undefined,
    cup,
    height_range: heightRange,
    age_range: ageRange,
    bust_range: bustRange,
    waist_range: waistRange,
    hip_range: hipRange,
    tags: tagFilters.length > 0 ? tagFilters.join(',') : undefined,
  }), [ageRange, bustRange, cup, heightRange, hipRange, keyword, limit, page, tagFilters, waistRange])

  const setRangeFilter = (setter: (value: string | undefined) => void) => (value: string | undefined) => {
    setter(value)
    setPage(1)
  }

  const query = useQuery({
    queryKey: queryKeys.actresses.list(params),
    queryFn: () => fetchActresses(params),
  })

  const tagOptionsQuery = useQuery({
    queryKey: queryKeys.actresses.tags(),
    queryFn: getActressTags,
  })

  const actresses = query.data?.items ?? []
  const total = query.data?.total ?? 0
  const crawlLinks = crawlTarget?.external_links ?? []
  const selectedCrawlLink = crawlLinks.find((link) => link.id === selectedLinkId) ?? crawlLinks[0]

  const openCrawlModal = (actress: ActressProfile) => {
    const links = actress.external_links ?? []
    if (links.length === 0) {
      message.warning('当前女优没有可爬取的关联 URL')
      return
    }
    setCrawlTarget(actress)
    setSelectedLinkId(links[0].id)
    setCrawlMode('incremental')
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
      setCrawlTarget(null)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提交爬取任务失败')
    } finally {
      setSubmittingCrawl(false)
    }
  }

  return (
    <div className={styles.page}>
      <section className={styles.toolbar} aria-label="女优列表筛选">
        <div className={styles.toolbarTitle}>
          <Typography.Title level={4} className={styles.pageTitle}>女优列表</Typography.Title>
          <Typography.Text type="secondary">共 {total} 位女优</Typography.Text>
        </div>
        <div className={styles.queryRail}>
          <div className={styles.filterControls}>
            <Input
              allowClear
              aria-label="搜索女优姓名或别名"
              prefix={<SearchOutlined />}
              placeholder="搜索姓名 / 别名"
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value)
                setPage(1)
              }}
              className={styles.searchInput}
            />
            <Select
              mode="tags"
              allowClear
              maxTagCount="responsive"
              aria-label="标签"
              placeholder="标签筛选"
              value={tagFilters}
              loading={tagOptionsQuery.isLoading}
              options={(tagOptionsQuery.data ?? []).map((tag) => ({ value: tag.name, label: tag.name }))}
              onChange={(values) => {
                setTagFilters(values)
                setPage(1)
              }}
              className={styles.tagFilterSelect}
            />
            <Button
              icon={<FilterOutlined />}
              aria-label="更多筛选"
              aria-expanded={advancedOpen}
              onClick={() => setAdvancedOpen((value) => !value)}
            >
              更多筛选
            </Button>
          </div>
        </div>
        {advancedOpen && (
          <section className={styles.advancedFilters} aria-label="女优高级筛选">
            <Select
              allowClear
              aria-label="罩杯"
              options={CUP_OPTIONS}
              placeholder="罩杯"
              value={cup}
              onChange={setRangeFilter(setCup)}
              className={styles.filterSelect}
            />
            <div className={styles.rangeGroup}>
              <Typography.Text className={styles.rangeLabel}>身高</Typography.Text>
              <Select
                allowClear
                aria-label="身高"
                options={HEIGHT_OPTIONS}
                placeholder="身高范围"
                value={heightRange}
                onChange={setRangeFilter(setHeightRange)}
                className={styles.filterSelect}
              />
            </div>
            <div className={styles.rangeGroup}>
              <Typography.Text className={styles.rangeLabel}>年龄</Typography.Text>
              <Select
                allowClear
                aria-label="年龄"
                options={AGE_OPTIONS}
                placeholder="年龄范围"
                value={ageRange}
                onChange={setRangeFilter(setAgeRange)}
                className={styles.filterSelect}
              />
            </div>
            <div className={styles.rangeGroup}>
              <Typography.Text className={styles.rangeLabel}>胸围</Typography.Text>
              <Select
                allowClear
                aria-label="胸围"
                options={BUST_OPTIONS}
                placeholder="胸围范围"
                value={bustRange}
                onChange={setRangeFilter(setBustRange)}
                className={styles.filterSelect}
              />
            </div>
            <div className={styles.rangeGroup}>
              <Typography.Text className={styles.rangeLabel}>腰围</Typography.Text>
              <Select
                allowClear
                aria-label="腰围"
                options={WAIST_OPTIONS}
                placeholder="腰围范围"
                value={waistRange}
                onChange={setRangeFilter(setWaistRange)}
                className={styles.filterSelect}
              />
            </div>
            <div className={styles.rangeGroup}>
              <Typography.Text className={styles.rangeLabel}>臀围</Typography.Text>
              <Select
                allowClear
                aria-label="臀围"
                options={HIP_OPTIONS}
                placeholder="臀围范围"
                value={hipRange}
                onChange={setRangeFilter(setHipRange)}
                className={styles.filterSelect}
              />
            </div>
          </section>
        )}
      </section>

      <Spin spinning={query.isLoading}>
        {actresses.length > 0 ? (
          <div className={styles.actressGrid}>
            {actresses.map((actress) => (
              <ActressCard
                key={actress.id}
                actress={actress}
                onCrawl={openCrawlModal}
                onOpen={(item) => navigate({ to: '/content/actresses/$id', params: { id: item.id } })}
              />
            ))}
          </div>
        ) : (
          <Empty description="暂无女优资料" className={styles.emptyState} />
        )}
      </Spin>

      {total > 0 && (
        <div className={styles.paginationBar}>
          <Pagination
            current={page}
            pageSize={limit}
            total={total}
            showSizeChanger
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            showTotal={(count) => `共 ${count} 位`}
            onChange={(nextPage, nextLimit) => {
              setPage(nextPage)
              if (nextLimit !== limit) {
                setLimit(nextLimit as 8 | 16 | 24 | 40)
              }
            }}
          />
        </div>
      )}

      <Modal
        title={crawlTarget ? `爬取 ${crawlTarget.display_name} 的影片` : '爬取影片'}
        open={Boolean(crawlTarget)}
        okText="开始爬取"
        cancelText="取消"
        confirmLoading={submittingCrawl}
        onOk={() => void submitCrawl()}
        onCancel={() => setCrawlTarget(null)}
      >
        <div className={styles.crawlModalBody}>
          {crawlLinks.length > 1 && (
            <Select
              aria-label="选择爬取 URL"
              value={selectedLinkId}
              options={crawlLinks.map((link) => ({ value: link.id, label: formatLinkLabel(link) }))}
              onChange={setSelectedLinkId}
            />
          )}
          {crawlLinks.length === 1 && selectedCrawlLink && (
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
    </div>
  )
}

export default ActressListPage
