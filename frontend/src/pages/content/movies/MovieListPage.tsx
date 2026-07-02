import { useCallback, useEffect, useState } from 'react'
import { Drawer, Image, Input, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getMovie, getMovies } from '@/api/movie'
import type { Movie } from '@/api/movie/types'

const PAGE_SIZE = 20

function MovieListPage() {
  const [movies, setMovies] = useState<Movie[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [current, setCurrent] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [sourceTaskName, setSourceTaskName] = useState('')
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const fetchMovies = useCallback(async (page: number) => {
    setLoading(true)
    try {
      const skip = (page - 1) * PAGE_SIZE
      const data = await getMovies({
        skip,
        limit: PAGE_SIZE,
        keyword: keyword || undefined,
        source_task_name: sourceTaskName || undefined,
      })
      setMovies(data.rows)
      setTotal(data.total)
    } finally {
      setLoading(false)
    }
  }, [keyword, sourceTaskName])

  useEffect(() => {
    void fetchMovies(current)
  }, [current, fetchMovies])

  const handleViewDetail = useCallback(async (movie: Movie) => {
    try {
      const detail = await getMovie(movie.id)
      setSelectedMovie(detail)
      setDrawerOpen(true)
    } catch {
      // ignore
    }
  }, [])

  const columns: ColumnsType<Movie> = [
    {
      title: '封面',
      dataIndex: 'cover',
      key: 'cover',
      width: 80,
      render: (cover: string) => (
        cover ? <Image src={cover} width={60} height={80} style={{ objectFit: 'cover' }} /> : '-'
      ),
    },
    {
      title: '番号',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '名称',
      dataIndex: 'source_name',
      key: 'source_name',
      ellipsis: true,
    },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      width: 80,
      render: (rating: number | null) => rating?.toFixed(1) ?? '-',
    },
    {
      title: '发行日期',
      dataIndex: 'release_date',
      key: 'release_date',
      width: 110,
    },
    {
      title: '时长',
      dataIndex: 'duration',
      key: 'duration',
      width: 80,
      render: (d: number) => (d > 0 ? `${d}分钟` : '-'),
    },
    {
      title: '演员',
      dataIndex: 'actors',
      key: 'actors',
      render: (actors: string[]) => (
        <Space size={4} wrap>
          {actors.slice(0, 3).map((a) => <Tag key={a}>{a}</Tag>)}
          {actors.length > 3 && <Tag>+{actors.length - 3}</Tag>}
        </Space>
      ),
    },
    {
      title: '来源任务',
      dataIndex: 'source_task_names',
      key: 'source_task_names',
      render: (names: string[]) => (
        <Space size={4} wrap>
          {names.map((n) => <Tag key={n} color="blue">{n}</Tag>)}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <a onClick={() => handleViewDetail(record)}>详情</a>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <h1>电影列表</h1>
      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索番号、名称、导演等"
          allowClear
          onSearch={(value) => {
            setKeyword(value)
            setCurrent(1)
          }}
          style={{ width: 250 }}
        />
        <Input.Search
          placeholder="来源任务名称"
          allowClear
          onSearch={(value) => {
            setSourceTaskName(value)
            setCurrent(1)
          }}
          style={{ width: 200 }}
        />
      </Space>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={movies}
        loading={loading}
        pagination={{
          current,
          total,
          pageSize: PAGE_SIZE,
          onChange: setCurrent,
        }}
      />
      <Drawer
        title={selectedMovie?.source_name || '电影详情'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={600}
      >
        {selectedMovie && (
          <div>
            <p><strong>番号：</strong>{selectedMovie.code}</p>
            <p><strong>发行日期：</strong>{selectedMovie.release_date}</p>
            <p><strong>时长：</strong>{selectedMovie.duration}分钟</p>
            <p><strong>导演：</strong>{selectedMovie.director || '-'}</p>
            <p><strong>制作商：</strong>{selectedMovie.maker || '-'}</p>
            <p><strong>系列：</strong>{selectedMovie.series || '-'}</p>
            <p><strong>评分：</strong>{selectedMovie.rating?.toFixed(1) ?? '-'}</p>
            <p><strong>演员：</strong>{selectedMovie.actors.join(', ') || '-'}</p>
            <p><strong>标签：</strong>{selectedMovie.tags.join(', ') || '-'}</p>
            {selectedMovie.magnets && selectedMovie.magnets.length > 0 && (
              <>
                <h3>磁力链接</h3>
                {selectedMovie.magnets.map((m) => (
                  <div key={m.id} style={{ marginBottom: 8 }}>
                    <Tag>{m.name}</Tag>
                    {m.size_text && <span>{m.size_text}</span>}
                    {m.has_chinese_sub && <Tag color="green">中字</Tag>}
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  )
}

export default MovieListPage
