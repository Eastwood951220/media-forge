import { Button, Space, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'

export interface MovieColumnsOptions {
  onViewDetail: (id: string) => void
  onPush?: (movie: Movie) => void
  onDelete?: (movie: Movie) => void
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

export function createMovieColumns({ onViewDetail, onPush, onDelete }: MovieColumnsOptions): ColumnsType<Movie> {
  return [
    { title: '番号', dataIndex: 'code', key: 'code', width: 120 },
    { title: '标题', dataIndex: 'source_name', key: 'source_name', ellipsis: true },
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
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 160,
      render: (_: unknown, record) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => onViewDetail(record._id)}>
            详情
          </Button>
          {onPush && (
            <Button type="link" size="small" onClick={() => onPush(record)}>
              推送
            </Button>
          )}
          {onDelete && (
            <Button type="link" danger size="small" onClick={() => onDelete(record)}>
              删除
            </Button>
          )}
        </Space>
      ),
    },
  ]
}
