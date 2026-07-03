import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import StoragePushModal from '../src/pages/content/movies/components/StoragePushModal'

const mockMovies = [
  { _id: 'movie-1', code: 'ABC-123', source_name: 'Test Movie', storage_locations: ['/data/movies'] },
]

describe('StoragePushModal', () => {
  it('renders single mode title', () => {
    render(
      <StoragePushModal
        open
        mode="single"
        movies={mockMovies}
        selectedRowKeys={['movie-1']}
        loading={false}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    expect(screen.getByText('推送存储')).toBeInTheDocument()
    expect(screen.getByText('ABC-123')).toBeInTheDocument()
  })

  it('renders batch mode title with count', () => {
    render(
      <StoragePushModal
        open
        mode="batch"
        movies={mockMovies}
        selectedRowKeys={['movie-1', 'movie-2']}
        loading={false}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    )

    expect(screen.getByText('批量推送存储')).toBeInTheDocument()
    expect(screen.getByText('已选择 2 条')).toBeInTheDocument()
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const onCancel = vi.fn()
    render(
      <StoragePushModal
        open
        mode="single"
        movies={mockMovies}
        selectedRowKeys={['movie-1']}
        loading={false}
        onCancel={onCancel}
        onSubmit={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalled()
  })
})
