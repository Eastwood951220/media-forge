import { useMemo, useState } from 'react'
import { SearchOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Avatar, Card, Empty, Input, Pagination, Spin, Typography } from 'antd'
import { fetchActresses } from '@/api/content/actresses'
import type { ActressProfile } from '@/api/content/actresses'
import { queryKeys } from '@/api/queryKeys'
import styles from './ActressPages.module.less'

const PAGE_SIZE_OPTIONS = ['8', '16', '24', '40']

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
  const params = useMemo(() => ({ page, limit, keyword: keyword.trim() || undefined }), [keyword, limit, page])

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
      </section>

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
