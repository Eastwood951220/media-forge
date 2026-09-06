import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import StoragePushModal from '../components/StoragePushModal'

const baseProps = {
  open: true,
  mode: 'single' as const,
  movies: [
    {
      _id: 'movie-1',
      code: 'AAA-001',
      source_name: 'Movie',
      storage_locations: ['A', 'B'],
    },
  ],
  selectedRowKeys: ['movie-1'],
  loading: false,
  defaultAlias: 'alias',
  onCancel: vi.fn(),
}

describe('StoragePushModal', () => {
  it('submits default single target without a selected storage location', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(<StoragePushModal {...baseProps} onSubmit={onSubmit} />)
    await user.click(screen.getByRole('button', { name: 'OK' }))

    expect(onSubmit).toHaveBeenCalledWith({
      alias: 'alias',
      storageMode: 'single',
      selectedStorageLocation: undefined,
    })
  })

  it('lets users choose one existing storage location for a single target push', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(<StoragePushModal {...baseProps} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('选择已有路径'))
    await user.click(screen.getByLabelText('已有路径'))
    await user.click(await screen.findByTitle('B'))
    await user.click(screen.getByRole('button', { name: 'OK' }))

    expect(onSubmit).toHaveBeenCalledWith({
      alias: 'alias',
      storageMode: 'single',
      selectedStorageLocation: 'B',
    })
  })

  it('builds existing storage location choices from all movies in the modal', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(
      <StoragePushModal
        {...baseProps}
        mode="batch"
        movies={[
          { _id: 'movie-1', code: 'AAA-001', storage_locations: ['A'] },
          { _id: 'movie-2', code: 'BBB-002', storage_locations: ['C'] },
        ]}
        selectedRowKeys={['movie-1', 'movie-2']}
        onSubmit={onSubmit}
      />,
    )
    fireEvent.click(screen.getByText('选择已有路径'))
    await user.click(screen.getByLabelText('已有路径'))
    await user.click(await screen.findByTitle('C'))
    await user.click(screen.getByRole('button', { name: 'OK' }))

    expect(onSubmit).toHaveBeenCalledWith({
      alias: 'alias',
      storageMode: 'single',
      selectedStorageLocation: 'C',
    })
  })

  it('lets users type a custom relative target path', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()

    render(<StoragePushModal {...baseProps} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('指定路径'))
    await user.type(screen.getByRole('textbox', { name: '指定路径' }), 'Custom/Sub')
    await user.click(screen.getByRole('button', { name: 'OK' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        alias: 'alias',
        storageMode: 'single',
        selectedStorageLocation: 'Custom/Sub',
      })
    })
  })
})
