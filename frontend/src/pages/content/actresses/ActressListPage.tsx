import { useMemo, useState } from 'react'
import { FilterOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Avatar, Button, Card, Empty, Input, InputNumber, Pagination, Spin, Typography } from 'antd'
import { fetchActresses } from '@/api/content/actresses'
import type { ActressProfile } from '@/api/content/actresses'
import { queryKeys } from '@/api/queryKeys'
import styles from './ActressPages.module.less'

const PAGE_SIZE_OPTIONS = ['8', '16', '24', '40']
const MEASUREMENT_FIELDS = [
  { key: 'bust', label: '胸围' },
  { key: 'waist', label: '腰围' },
  { key: 'hip', label: '臀围' },
] as const

function ActressCard({ actress, onOpen }: { actress: ActressProfile; onOpen: (actress: ActressProfile) => void }) {
  return (
    <Card
      hoverable
      className={styles.actressCard}
      cover={
        <div className={styles.actressCover}>
          {actress.image_url ? (
            <img src={actress.image_url} alt={actress.display_name} loading="lazy" />
          ) : (
            <Avatar size={72} icon={<UserOutlined />} />
          )}
        </div>
      }
      onClick={() => onOpen(actress)}
    >
      <Typography.Title level={5} className={styles.actressName}>
        {actress.display_name}
      </Typography.Title>
      <Typography.Text type="secondary" className={styles.actressReading}>
        {actress.reading || actress.aliases[0] || '未记录读音'}
      </Typography.Text>
    </Card>
  )
}

function ActressListPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState<8 | 16 | 24 | 40>(24)
  const [keyword, setKeyword] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [cup, setCup] = useState('')
  const [heightMin, setHeightMin] = useState<number | null>(null)
  const [heightMax, setHeightMax] = useState<number | null>(null)
  const [bustMin, setBustMin] = useState<number | null>(null)
  const [bustMax, setBustMax] = useState<number | null>(null)
  const [waistMin, setWaistMin] = useState<number | null>(null)
  const [waistMax, setWaistMax] = useState<number | null>(null)
  const [hipMin, setHipMin] = useState<number | null>(null)
  const [hipMax, setHipMax] = useState<number | null>(null)
  const params = useMemo(() => ({
    page,
    limit,
    keyword: keyword.trim() || undefined,
    cup: cup.trim() || undefined,
    height_min: heightMin ?? undefined,
    height_max: heightMax ?? undefined,
    bust_min: bustMin ?? undefined,
    bust_max: bustMax ?? undefined,
    waist_min: waistMin ?? undefined,
    waist_max: waistMax ?? undefined,
    hip_min: hipMin ?? undefined,
    hip_max: hipMax ?? undefined,
  }), [bustMax, bustMin, cup, heightMax, heightMin, hipMax, hipMin, keyword, limit, page, waistMax, waistMin])

  const setNumberFilter = (setter: (value: number | null) => void) => (value: number | null) => {
    setter(value)
    setPage(1)
  }

  const query = useQuery({
    queryKey: queryKeys.actresses.list(params),
    queryFn: () => fetchActresses(params),
  })

  const actresses = query.data?.items ?? []
  const total = query.data?.total ?? 0

  return (
    <div className={styles.page}>
      <section className={styles.toolbar} aria-label="女优列表筛选">
        <div>
          <Typography.Title level={4} className={styles.pageTitle}>女优列表</Typography.Title>
          <Typography.Text type="secondary">共 {total} 位女优</Typography.Text>
        </div>
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
          <Button
            icon={<FilterOutlined />}
            aria-label="更多筛选"
            aria-expanded={advancedOpen}
            onClick={() => setAdvancedOpen((value) => !value)}
          >
            更多筛选
          </Button>
        </div>
      </section>

      {advancedOpen && (
        <section className={styles.advancedFilters} aria-label="女优高级筛选">
          <Input
            allowClear
            aria-label="罩杯"
            placeholder="罩杯"
            value={cup}
            onChange={(event) => {
              setCup(event.target.value)
              setPage(1)
            }}
            className={styles.compactInput}
          />
          <div className={styles.rangeGroup}>
            <Typography.Text className={styles.rangeLabel}>身高</Typography.Text>
            <InputNumber
              aria-label="最低身高"
              min={0}
              placeholder="最低"
              value={heightMin}
              onChange={setNumberFilter(setHeightMin)}
            />
            <InputNumber
              aria-label="最高身高"
              min={0}
              placeholder="最高"
              value={heightMax}
              onChange={setNumberFilter(setHeightMax)}
            />
          </div>
          {MEASUREMENT_FIELDS.map((field) => {
            const minValue = field.key === 'bust' ? bustMin : field.key === 'waist' ? waistMin : hipMin
            const maxValue = field.key === 'bust' ? bustMax : field.key === 'waist' ? waistMax : hipMax
            const setMin = field.key === 'bust' ? setBustMin : field.key === 'waist' ? setWaistMin : setHipMin
            const setMax = field.key === 'bust' ? setBustMax : field.key === 'waist' ? setWaistMax : setHipMax
            return (
              <div key={field.key} className={styles.rangeGroup}>
                <Typography.Text className={styles.rangeLabel}>{field.label}</Typography.Text>
                <InputNumber
                  aria-label={`最低${field.label}`}
                  min={0}
                  placeholder="最低"
                  value={minValue}
                  onChange={setNumberFilter(setMin)}
                />
                <InputNumber
                  aria-label={`最高${field.label}`}
                  min={0}
                  placeholder="最高"
                  value={maxValue}
                  onChange={setNumberFilter(setMax)}
                />
              </div>
            )
          })}
        </section>
      )}

      <Spin spinning={query.isLoading}>
        {actresses.length > 0 ? (
          <div className={styles.actressGrid}>
            {actresses.map((actress) => (
              <ActressCard
                key={actress.id}
                actress={actress}
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
    </div>
  )
}

export default ActressListPage
