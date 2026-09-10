import { Space, Tag } from 'antd'
import type { CSSProperties } from 'react'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'
import ResponsiveActions, { type ResponsiveAction } from '@/components/ResponsiveActions'
import { useImageBlurStore } from '@/stores/useImageBlurStore'
import styles from '../MovieListPage.module.less'

export interface MovieColumnsOptions {
  onViewDetail: (id: string) => void
  onPush?: (movie: Movie) => void
  onDelete?: (movie: Movie) => void
  onCd2Sync?: (movie: Movie) => void
  onRefreshMagnets?: (movie: Movie) => void
  cd2SyncingId?: string | null
  magnetRefreshingId?: string | null
}

const storageStatusColor: Record<string, string> = {
  not_stored: 'default',
  storing: 'processing',
  stored: 'success',
}

const storageStatusText: Record<string, string> = {
  not_stored: '未存储',
  storing: '入库中',
  stored: '已存储',
}

function unique(values: string[] | undefined) {
  return [...new Set(values || [])]
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '-'
}

function mediaBackdropStyle(url: string): CSSProperties {
  return { '--media-bg': `url("${url}")` } as CSSProperties
}

function MovieCoverCell({ movie }: { movie: Movie }) {
  const blurEnabled = useImageBlurStore((state) => state.enabled)
  if (!movie.cover) return <span>-</span>
  return (
    <div className={styles.movieCoverCell} style={mediaBackdropStyle(movie.cover)}>
      <img
        src={movie.cover}
        alt={movie.code}
        className={blurEnabled ? 'app-blurred-media' : undefined}
        loading="lazy"
        referrerPolicy="no-referrer"
      />
    </div>
  )
}

export function createMovieColumns({ onViewDetail, onPush, onDelete, onCd2Sync, onRefreshMagnets, cd2SyncingId, magnetRefreshingId }: MovieColumnsOptions): ColumnsType<Movie> {
  return [
    {
      title: '封面',
      dataIndex: 'cover',
      key: 'cover',
      width: 76,
      render: (_cover: string, record) => <MovieCoverCell movie={record} />,
    },
    { title: '番号',
      dataIndex: 'code',
      key: 'code',
      width: 120
    },
    { title: '标题',
      dataIndex: 'source_name',
      key: 'source_name',
      width: 400,
      ellipsis: true
    },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      render: (value: number | null) => (value != null ? value.toFixed(2) : '-'),
    },
    {
      title: '发行日期',
      dataIndex: 'release_date',
      key: 'release_date',
      width: 160,
    },
    {
      title: '时长',
      dataIndex: 'duration',
      key: 'duration',
      width: 100,
      render: (value: number) => (value != null ? `${value}分` : '-'),
    },
    {
      title: '演员',
      dataIndex: 'actors',
      key: 'actors',
      width: 180,
      ellipsis: true,
      render: (actors: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(actors).slice(0, 3).map((actor) => <Tag key={actor}>{actor}</Tag>)}
          {unique(actors).length > 3 && <Tag>+{unique(actors).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 240,
      ellipsis: true,
      render: (tags: string[]) => (
        <Space size={[0, 4]} wrap>
          {unique(tags).slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          {unique(tags).length > 3 && <Tag>+{unique(tags).length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '存储状态',
      key: 'storage_status',
      width: 100,
      render: (_: unknown, record) => {
        const status = record.storage_status || record.storage_summary?.storage_status || 'not_stored'
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
      },
    },
    {
      title: '抓取时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: formatDateTime,
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 220,
      render: (_: unknown, record) => {
        const actions: ResponsiveAction[] = [
          { key: 'detail', label: '详情', onClick: () => onViewDetail(record._id) },
          ...(onPush ? [{ key: 'push', label: '推送', onClick: () => onPush(record) }] : []),
          ...(onCd2Sync
            ? [{
                key: 'cd2-sync',
                label: 'CD2同步',
                disabled: cd2SyncingId === record._id,
                loading: cd2SyncingId === record._id,
                onClick: () => onCd2Sync(record),
              }]
            : []),
          ...(onRefreshMagnets
            ? [{
                key: 'refresh-magnets',
                label: '更新磁力',
                disabled: magnetRefreshingId === record._id,
                loading: magnetRefreshingId === record._id,
                onClick: () => onRefreshMagnets(record),
              }]
            : []),
          ...(onDelete ? [{ key: 'delete', label: '删除', danger: true, onClick: () => onDelete(record) }] : []),
        ]

        return <ResponsiveActions actions={actions} />
      },
    },
  ]
}
