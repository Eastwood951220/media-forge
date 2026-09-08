import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BaseListPage from '../src/components/BaseListPage'
import type { ColumnsType } from 'antd/es/table'

type Row = {
  id: number
  name: string
  code?: string
}

const columns: ColumnsType<Row> = [
  { title: '名称', dataIndex: 'name', key: 'name' },
]

describe('BaseListPage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders query, toolbar, table data, and refreshes', async () => {
    const onRefresh = vi.fn()

    render(
      <BaseListPage<Row>
        rowKey="id"
        columns={columns}
        dataSource={[{ id: 1, name: '影片A' }]}
        queryNode={<input aria-label="关键词" />}
        toolbarLeft={<button type="button">批量操作</button>}
        onRefresh={onRefresh}
      />,
    )

    expect(screen.getByLabelText('关键词')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '批量操作' })).toBeInTheDocument()
    expect(screen.getByText('影片A')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '刷新列表' }))

    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('toggles the query area and applies adaptive table height', async () => {
    let resizeCallback: ResizeObserverCallback | undefined
    const OriginalResizeObserver = globalThis.ResizeObserver

    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    }

    const { container } = render(
      <BaseListPage<Row>
        rowKey="id"
        columns={columns}
        dataSource={[{ id: 1, name: '影片A' }]}
        queryNode={<input aria-label="关键词" />}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: '隐藏搜索' }))
    expect(screen.queryByLabelText('关键词')).not.toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: '显示搜索' }))
    expect(screen.getByLabelText('关键词')).toBeVisible()

    act(() => {
      resizeCallback?.([
        { contentRect: { height: 520 } as DOMRectReadOnly } as ResizeObserverEntry,
      ], {} as ResizeObserver)
    })

    const tableBody = container.querySelector('.ant-table-body') as HTMLElement | null
    expect(tableBody?.style.maxHeight).toBe('400px')

    globalThis.ResizeObserver = OriginalResizeObserver
  })

  it('keeps the previous table height when hidden layout reports zero before returning', () => {
    const resizeCallbacks: ResizeObserverCallback[] = []
    const OriginalResizeObserver = globalThis.ResizeObserver

    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallbacks.push(callback)
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    }

    try {
      const { container, unmount } = render(
        <BaseListPage<Row>
          rowKey="id"
          columnSettingsKey="height-list"
          columns={columns}
          dataSource={[{ id: 1, name: '影片A' }]}
        />,
      )

      act(() => {
        resizeCallbacks[0]?.([
          { contentRect: { height: 520 } as DOMRectReadOnly } as ResizeObserverEntry,
        ], {} as ResizeObserver)
      })

      const tableBody = container.querySelector('.ant-table-body') as HTMLElement | null
      expect(tableBody?.style.maxHeight).toBe('400px')

      act(() => {
        resizeCallbacks[0]?.([
          { contentRect: { height: 0 } as DOMRectReadOnly } as ResizeObserverEntry,
        ], {} as ResizeObserver)
      })

      expect(tableBody?.style.maxHeight).toBe('400px')

      unmount()
      const remounted = render(
        <BaseListPage<Row>
          rowKey="id"
          columnSettingsKey="height-list"
          columns={columns}
          dataSource={[{ id: 1, name: '影片A' }]}
        />,
      )

      const remountedTableBody = remounted.container.querySelector('.ant-table-body') as HTMLElement | null
      expect(remountedTableBody?.style.maxHeight).toBe('400px')
    } finally {
      globalThis.ResizeObserver = OriginalResizeObserver
    }
  })

  it('does not update cached table height on route return unless the viewport changes', () => {
    const resizeCallbacks: ResizeObserverCallback[] = []
    const OriginalResizeObserver = globalThis.ResizeObserver
    const originalInnerWidth = window.innerWidth
    const originalInnerHeight = window.innerHeight

    globalThis.ResizeObserver = class ResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallbacks.push(callback)
      }

      observe() {}
      unobserve() {}
      disconnect() {}
    }

    try {
      const { container, unmount } = render(
        <BaseListPage<Row>
          rowKey="id"
          columnSettingsKey="height-return-list"
          columns={columns}
          dataSource={[{ id: 1, name: '影片A' }]}
        />,
      )

      act(() => {
        resizeCallbacks[0]?.([
          { contentRect: { height: 520 } as DOMRectReadOnly } as ResizeObserverEntry,
        ], {} as ResizeObserver)
      })

      const tableBody = container.querySelector('.ant-table-body') as HTMLElement | null
      expect(tableBody?.style.maxHeight).toBe('400px')

      unmount()
      const remounted = render(
        <BaseListPage<Row>
          rowKey="id"
          columnSettingsKey="height-return-list"
          columns={columns}
          dataSource={[{ id: 1, name: '影片A' }]}
        />,
      )

      const remountedTableBody = remounted.container.querySelector('.ant-table-body') as HTMLElement | null
      expect(remountedTableBody?.style.maxHeight).toBe('400px')

      act(() => {
        resizeCallbacks[1]?.([
          { contentRect: { height: 500 } as DOMRectReadOnly } as ResizeObserverEntry,
        ], {} as ResizeObserver)
      })

      expect(remountedTableBody?.style.maxHeight).toBe('400px')

      Object.defineProperty(window, 'innerHeight', {
        configurable: true,
        value: originalInnerHeight + 1,
      })
      act(() => {
        window.dispatchEvent(new Event('resize'))
      })

      act(() => {
        resizeCallbacks[resizeCallbacks.length - 1]?.([
          { contentRect: { height: 500 } as DOMRectReadOnly } as ResizeObserverEntry,
        ], {} as ResizeObserver)
      })

      expect(remountedTableBody?.style.maxHeight).toBe('380px')
    } finally {
      globalThis.ResizeObserver = OriginalResizeObserver
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        value: originalInnerWidth,
      })
      Object.defineProperty(window, 'innerHeight', {
        configurable: true,
        value: originalInnerHeight,
      })
    }
  })

  it('applies persisted column visibility and order when a settings key is provided', () => {
    localStorage.setItem(
      'media-forge:list-columns:test-list',
      JSON.stringify({
        order: ['code', 'name'],
        hidden: ['name'],
      }),
    )

    render(
      <BaseListPage<Row>
        rowKey="id"
        columnSettingsKey="test-list"
        columns={[
          { title: '名称', dataIndex: 'name', key: 'name' },
          { title: '番号', dataIndex: 'code', key: 'code' },
        ]}
        dataSource={[{ id: 1, name: '影片A', code: 'AAA-001' }]}
      />,
    )

    expect(screen.getByRole('button', { name: '列设置' })).toBeInTheDocument()
    expect(screen.getByText('番号')).toBeInTheDocument()
    expect(screen.getByText('AAA-001')).toBeInTheDocument()
    expect(screen.queryByText('名称')).not.toBeInTheDocument()
    expect(screen.queryByText('影片A')).not.toBeInTheDocument()
  })
})
