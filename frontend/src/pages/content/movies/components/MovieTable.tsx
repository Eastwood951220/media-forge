import { Button, Space, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Movie } from '@/api/movie/types'

export interface MovieColumnsOptions {
  onViewDetail: (id: string) => void
}

const storageStatusColor: Record<string, string> = {
  pending: 'processing',
  running: 'processing',
  waiting_download: 'processing',
  waiting_retry: 'warning',
  downloading: 'processing',
  moving: 'processing',
  completed: 'success',
  failed: 'error',
  retryable: 'warning',
  missing: 'error',
  skipped: 'default',
}

const storageStatusText: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  waiting_download: '等待下载',
  waiting_retry: '等待重试',
  downloading: '下载中',
  moving: '移动中',
  completed: '已完成',
  failed: '失败',
  retryable: '可重试',
  missing: '文件缺失',
  skipped: '已跳过',
}

function unique(values: string[] | undefined) {
  return [...new Set(values || [])]
}

export function createMovieColumns({ onViewDetail }: MovieColumnsOptions): ColumnsType<Movie> {
  return [
    { title: '番号', dataIndex: 'code', key: 'code', width: 120 },
    { title: '标题', dataIndex: 'source_name', key: 'source_name', ellipsis: true },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      sorter: true,
      render: (value: number | null) => (value != null ? value.toFixed(2) : '-'),
    },
    {
      title: '发行日期',
      dataIndex: 'release_date',
      key: 'release_date',
      width: 160,
      sorter: true,
      defaultSortOrder: 'descend',
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
        const status = record.storage_summary?.last_status
        if (!status) return <Typography.Text type="secondary">-</Typography.Text>
        return <Tag color={storageStatusColor[status]}>{storageStatusText[status] || status}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 100,
      render: (_: unknown, record) => (
        <Button type="link" size="small" onClick={() => onViewDetail(record._id)}>
          详情
        </Button>
      ),
    },
  ]
}
