import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
} as Movie

describe('MovieTable actions', () => {
  it('renders detail directly and moves row actions into more menu', async () => {
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
    fireEvent.mouseDown(screen.getByRole('button', { name: /更多/ }))

    await waitFor(() => expect(screen.getByText('推送')).toBeInTheDocument())
    expect(screen.getByText('CD2同步')).toBeInTheDocument()
    expect(screen.getByText('更新磁力')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
  })
})
