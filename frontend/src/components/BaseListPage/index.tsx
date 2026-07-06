import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Table, Tooltip } from 'antd'
import { RedoOutlined, SearchOutlined } from '@ant-design/icons'
import type { BaseListPageProps } from './types'
import styles from './index.module.less'

const TABLE_SCROLL_OFFSET = 120
const MIN_TABLE_SCROLL_Y = 160

function useElementHeight<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [height, setHeight] = useState(0)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return

      const nextHeight = Math.round(entry.contentRect.height)
      setHeight((previousHeight) => (previousHeight === nextHeight ? previousHeight : nextHeight))
    })

    resizeObserver.observe(element)
    return () => resizeObserver.disconnect()
  }, [])

  return { ref, height }
}

export default function BaseListPage<T extends object>({
  rowKey,
  columns,
  dataSource,
  loading = false,
  pagination,
  rowSelection,
  queryNode,
  toolbarLeft,
  tableProps,
  expandable,
  onRefresh,
  queryVisibleDefault = true,
}: BaseListPageProps<T>) {
  const [queryVisible, setQueryVisible] = useState(queryVisibleDefault)
  const { ref: tableWrapperRef, height: tableWrapperHeight } = useElementHeight<HTMLDivElement>()

  const tableScrollY = useMemo(() => {
    if (tableWrapperHeight <= 0) return undefined
    return Math.max(tableWrapperHeight - TABLE_SCROLL_OFFSET, MIN_TABLE_SCROLL_Y)
  }, [tableWrapperHeight])

  return (
    <div className={styles.baseListPage}>
      {queryNode && (
        <Card className={`${styles.queryCard} ${queryVisible ? '' : styles.hidden}`} size="small">
          {queryNode}
        </Card>
      )}

      <Card className={styles.tableCard} size="small">
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>{toolbarLeft}</div>
          <div className={styles.toolbarRight}>
            {queryNode && (
              <Tooltip title={queryVisible ? '隐藏搜索' : '显示搜索'}>
                <Button
                  aria-label={queryVisible ? '隐藏搜索' : '显示搜索'}
                  type="text"
                  icon={<SearchOutlined />}
                  onClick={() => setQueryVisible((visible) => !visible)}
                />
              </Tooltip>
            )}
            {onRefresh && (
              <Tooltip title="刷新">
                <Button
                  aria-label="刷新列表"
                  type="text"
                  icon={<RedoOutlined />}
                  onClick={onRefresh}
                />
              </Tooltip>
            )}
          </div>
        </div>

        <div ref={tableWrapperRef} className={styles.tableWrapper}>
          <Table<T>
            rowKey={rowKey}
            columns={columns}
            dataSource={dataSource}
            loading={loading}
            pagination={pagination}
            rowSelection={rowSelection}
            expandable={expandable}
            tableLayout="fixed"
            scroll={{ y: tableScrollY, x: 'max-content' }}
            {...tableProps}
          />
        </div>
      </Card>
    </div>
  )
}
