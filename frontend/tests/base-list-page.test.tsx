import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import BaseListPage from '../src/components/BaseListPage'
import type { ColumnsType } from 'antd/es/table'

type Row = {
  id: number
  name: string
}

const columns: ColumnsType<Row> = [
  { title: '名称', dataIndex: 'name', key: 'name' },
]

describe('BaseListPage', () => {
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
})
