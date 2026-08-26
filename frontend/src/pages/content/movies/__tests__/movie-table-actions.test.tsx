import { fireEvent, render, screen } from '@testing-library/react'
import { Table } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import type { Movie } from '@/api/movie/types'
import { createMovieColumns } from '../components/MovieTable'

const movie = {
  _id: 'movie-1',
  id: 'movie-1',
  code: 'AAA-001',
  source_name: 'Movie',
  actors: [],
  tags: [],
  storage_status: 'not_stored',
  storage_summary: {},
} as unknown as Movie

describe('MovieTable actions', () => {
  it('renders all actions inline until the responsive group measures constrained width', () => {
    const onViewDetail = vi.fn()
    const onPush = vi.fn()
    const onCd2Sync = vi.fn()
    const onRefreshMagnets = vi.fn()
    const onDelete = vi.fn()
    render(
      <Table
        rowKey="_id"
        dataSource={[movie]}
        columns={createMovieColumns({ onViewDetail, onPush, onCd2Sync, onRefreshMagnets, onDelete })}
        pagination={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '详情' }))
    expect(onViewDetail).toHaveBeenCalledWith('movie-1')
    expect(screen.getByRole('button', { name: '推送' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CD2同步' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '更新磁力' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /更多/ })).not.toBeInTheDocument()
  })

  it('fixes the action column to the right side', () => {
    const columns = createMovieColumns({
      onViewDetail: vi.fn(),
      onPush: vi.fn(),
      onCd2Sync: vi.fn(),
      onRefreshMagnets: vi.fn(),
      onDelete: vi.fn(),
    })

    expect(columns.find((column) => column.key === 'action')).toMatchObject({
      fixed: 'right',
    })
  })
})
