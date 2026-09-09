import { ArrowLeftOutlined, LinkOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Avatar, Button, Descriptions, Empty, Image, Spin, Tag, Typography } from 'antd'
import { fetchActress } from '@/api/content/actresses'
import { queryKeys } from '@/api/queryKeys'
import styles from './ActressPages.module.less'

function formatDate(value: string | null) {
  return value || '-'
}

function ActressDetailPage() {
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { id: string }
  const query = useQuery({
    queryKey: queryKeys.actresses.detail(params.id),
    queryFn: () => fetchActress(params.id),
    enabled: Boolean(params.id),
  })
  const actress = query.data

  return (
    <div className={styles.page}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate({ to: '/content/actresses' })}>
        返回
      </Button>

      <Spin spinning={query.isLoading}>
        {actress ? (
          <>
            <section className={styles.detailHeader}>
              <div className={styles.detailPortrait}>
                {actress.image_url ? (
                  <Image src={actress.image_url} alt={actress.display_name} preview={false} />
                ) : (
                  <Avatar size={96} icon={<UserOutlined />} />
                )}
              </div>
              <div className={styles.detailTitleBlock}>
                <Typography.Title level={3} className={styles.detailTitle}>{actress.display_name}</Typography.Title>
                <Typography.Text type="secondary">{actress.reading || '未记录读音'}</Typography.Text>
                <div className={styles.aliasList}>
                  {actress.aliases.map((alias) => (
                    <Tag key={alias}>{alias}</Tag>
                  ))}
                </div>
                {actress.source_url && (
                  <Button
                    icon={<LinkOutlined />}
                    href={actress.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    avjoho
                  </Button>
                )}
              </div>
            </section>

            <section className={styles.detailSection}>
              <Typography.Title level={4}>资料</Typography.Title>
              <Descriptions bordered column={{ xs: 1, sm: 2, lg: 3 }} size="small">
                <Descriptions.Item label="出道日期">{formatDate(actress.debut_date)}</Descriptions.Item>
                <Descriptions.Item label="出生日期">{formatDate(actress.birth_date)}</Descriptions.Item>
                <Descriptions.Item label="身高">{actress.height_cm ? `${actress.height_cm}cm` : '-'}</Descriptions.Item>
                <Descriptions.Item label="三围">
                  {actress.bust_cm || actress.waist_cm || actress.hip_cm
                    ? `B${actress.bust_cm ?? '-'} W${actress.waist_cm ?? '-'} H${actress.hip_cm ?? '-'}`
                    : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="罩杯">{actress.cup || '-'}</Descriptions.Item>
                <Descriptions.Item label="出生地">{actress.birthplace || '-'}</Descriptions.Item>
                <Descriptions.Item label="血型">{actress.blood_type || '-'}</Descriptions.Item>
                <Descriptions.Item label="专属厂商">{actress.exclusive_maker || '-'}</Descriptions.Item>
                <Descriptions.Item label="兴趣特长">{actress.hobbies || '-'}</Descriptions.Item>
              </Descriptions>
              {actress.biography && <Typography.Paragraph className={styles.biography}>{actress.biography}</Typography.Paragraph>}
            </section>

            <section className={styles.detailSection}>
              <Typography.Title level={4}>最近影片</Typography.Title>
              {actress.recent_movies.length > 0 ? (
                <div className={styles.movieGrid}>
                  {actress.recent_movies.map((movie) => (
                    <article key={movie.id} className={styles.movieCard}>
                      <div className={styles.movieCover}>
                        {movie.cover ? <img src={movie.cover} alt={movie.title || movie.code} loading="lazy" /> : <VideoFallback />}
                      </div>
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
