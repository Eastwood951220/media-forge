import { ArrowLeftOutlined, LinkOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Avatar, Button, Empty, Image, Spin, Typography } from 'antd'
import { fetchActress } from '@/api/content/actresses'
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

function ActressDetailPage() {
  const navigate = useNavigate()
  const params = useParams({ strict: false }) as { id: string }
  const query = useQuery({
    queryKey: queryKeys.actresses.detail(params.id),
    queryFn: () => fetchActress(params.id),
    enabled: Boolean(params.id),
  })
  const actress = query.data
  const externalLinks = actress?.external_links ?? []
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
              <div className={styles.detailPortrait}>
                {actress.image_url ? (
                  <Image src={actress.image_url} alt={actress.display_name} preview={false} />
                ) : (
                  <Avatar size={96} icon={<UserOutlined />} />
                )}
              </div>
              <div className={styles.detailTitleBlock}>
                <div className={styles.detailNameRow}>
                  <div className={styles.detailNameText}>
                    <Typography.Title level={3} className={styles.detailTitle}>{actress.display_name}</Typography.Title>
                    <Typography.Text type="secondary">{actress.reading || '未记录读音'}</Typography.Text>
                  </div>
                  <div className={styles.sourceActions}>
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
