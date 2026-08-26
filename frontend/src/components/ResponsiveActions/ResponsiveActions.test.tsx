import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ResponsiveActions from './ResponsiveActions'

let resizeCallback: ResizeObserverCallback | undefined
const OriginalResizeObserver = globalThis.ResizeObserver

function resize(width: number) {
  act(() => {
    resizeCallback?.([
      { contentRect: { width } as DOMRectReadOnly } as ResizeObserverEntry,
    ], {} as ResizeObserver)
  })
}

describe('ResponsiveActions', () => {
  beforeEach(() => {
    resizeCallback = undefined
    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    }
  })

  afterEach(() => {
    globalThis.ResizeObserver = OriginalResizeObserver
  })

  it('keeps the primary action and more button when width is constrained', async () => {
    const user = userEvent.setup()
    render(
      <ResponsiveActions
        actions={[
          { key: 'detail', label: '详情', onClick: vi.fn() },
          { key: 'stop', label: '停止', onClick: vi.fn() },
          { key: 'delete', label: '删除', danger: true, onClick: vi.fn() },
        ]}
      />,
    )

    resize(112)

    expect(screen.getByRole('button', { name: '详情' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /更多/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '停止' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /更多/ }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(within(menu).getByRole('button', { name: '删除' })).toBeInTheDocument()
  })

  it('shows every action inline and hides more when width can fit them all', () => {
    render(
      <ResponsiveActions
        actions={[
          { key: 'detail', label: '详情', onClick: vi.fn() },
          { key: 'stop', label: '停止', onClick: vi.fn() },
          { key: 'delete', label: '删除', danger: true, onClick: vi.fn() },
        ]}
      />,
    )

    resize(260)

    expect(screen.getByRole('button', { name: '详情' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '停止' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /更多/ })).not.toBeInTheDocument()
  })
})
