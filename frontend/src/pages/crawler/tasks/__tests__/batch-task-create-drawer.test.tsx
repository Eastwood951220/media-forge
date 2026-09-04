import { App } from 'antd'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PropsWithChildren } from 'react'
import BatchTaskCreateDrawer from '../components/BatchTaskCreateDrawer'

function wrapper({ children }: PropsWithChildren) {
  return <App>{children}</App>
}

describe('BatchTaskCreateDrawer', () => {
  const onSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('blocks empty input before submit', async () => {
    render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    fireEvent.click(screen.getByRole('button', { name: '保 存' }))

    expect(await screen.findByText('请至少输入 1 个 URL')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('normalizes multiline URLs and sends default options', async () => {
    render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    await userEvent.type(
      screen.getByLabelText('URL 列表'),
      ' https://javdb.com/actors/a {enter}{enter}https://javdb.com/series/b ',
    )
    fireEvent.click(screen.getByRole('button', { name: '保 存' }))

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        urls: ['https://javdb.com/actors/a', 'https://javdb.com/series/b'],
        has_magnet: true,
        has_chinese_sub: false,
        sort_type: 0,
        is_skip: false,
      })
    })
  })

  it('loads failed urls when partial failure result is retried', async () => {
    const { rerender } = render(
      <BatchTaskCreateDrawer
        open
        submitting={false}
        failedUrls={[]}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
      { wrapper },
    )

    rerender(
      <App>
        <BatchTaskCreateDrawer
          open
          submitting={false}
          failedUrls={['https://javdb.com/actors/bad']}
          onCancel={vi.fn()}
          onSubmit={onSubmit}
        />
      </App>,
    )

    expect(within(screen.getByRole('dialog')).getByLabelText('URL 列表')).toHaveValue('https://javdb.com/actors/bad')
  })
})
