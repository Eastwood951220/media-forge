import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Checkbox, Popover, Table, Tooltip } from 'antd'
import { HolderOutlined, RedoOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import type { BaseListPageProps } from './types'
import styles from './index.module.less'

const TABLE_SCROLL_OFFSET = 120
const MIN_TABLE_SCROLL_Y = 160
const COLUMN_SETTINGS_STORAGE_PREFIX = 'media-forge:list-columns:'
const tableHeightCache = new Map<string, number>()

type ColumnSettings = {
  order: string[]
  hidden: string[]
}

function getColumnId<T extends object>(
  column: BaseListPageProps<T>['columns'][number],
  index: number,
) {
  if (column.key !== undefined && column.key !== null) return String(column.key)
  if ('dataIndex' in column && column.dataIndex !== undefined && column.dataIndex !== null) {
    return Array.isArray(column.dataIndex) ? column.dataIndex.join('.') : String(column.dataIndex)
  }
  return `column-${index}`
}

function getColumnLabel<T extends object>(
  column: BaseListPageProps<T>['columns'][number],
  fallback: string,
) {
  if (typeof column.title === 'string' || typeof column.title === 'number') {
    return String(column.title)
  }
  return fallback
}

function createColumnItems<T extends object>(columns: BaseListPageProps<T>['columns']) {
  return columns.map((column, index) => {
    const id = getColumnId(column, index)
    return {
      id,
      label: getColumnLabel(column, id),
      column,
      index,
    }
  })
}

function normalizeColumnSettings(settings: ColumnSettings, columnIds: string[]): ColumnSettings {
  const idSet = new Set(columnIds)
  const order = settings.order.filter((id, index, list) => idSet.has(id) && list.indexOf(id) === index)
  const hidden = settings.hidden.filter((id, index, list) => idSet.has(id) && list.indexOf(id) === index)

  for (const id of columnIds) {
    if (!order.includes(id)) order.push(id)
  }

  return { order, hidden }
}

function readColumnSettings(storageKey: string | undefined, columnIds: string[]): ColumnSettings {
  if (!storageKey || typeof window === 'undefined') {
    return normalizeColumnSettings({ order: [], hidden: [] }, columnIds)
  }

  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return normalizeColumnSettings({ order: [], hidden: [] }, columnIds)
    const parsed = JSON.parse(raw) as Partial<ColumnSettings>
    return normalizeColumnSettings(
      {
        order: Array.isArray(parsed.order) ? parsed.order.map(String) : [],
        hidden: Array.isArray(parsed.hidden) ? parsed.hidden.map(String) : [],
      },
      columnIds,
    )
  } catch {
    return normalizeColumnSettings({ order: [], hidden: [] }, columnIds)
  }
}

function writeColumnSettings(storageKey: string | undefined, settings: ColumnSettings) {
  if (!storageKey || typeof window === 'undefined') return
  window.localStorage.setItem(storageKey, JSON.stringify(settings))
}

function useElementHeight<T extends HTMLElement>(cacheKey?: string) {
  const ref = useRef<T | null>(null)
  const [height, setHeight] = useState(() => cacheKey ? tableHeightCache.get(cacheKey) ?? 0 : 0)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return

      const nextHeight = Math.round(entry.contentRect.height)
      if (nextHeight <= 0) return

      if (cacheKey) {
        tableHeightCache.set(cacheKey, nextHeight)
      }
      setHeight((previousHeight) => (previousHeight === nextHeight ? previousHeight : nextHeight))
    })

    resizeObserver.observe(element)
    return () => resizeObserver.disconnect()
  }, [cacheKey])

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
  columnSettingsKey,
}: BaseListPageProps<T>) {
  const [queryVisible, setQueryVisible] = useState(queryVisibleDefault)
  const { ref: tableWrapperRef, height: tableWrapperHeight } = useElementHeight<HTMLDivElement>(columnSettingsKey)
  const columnItems = useMemo(() => createColumnItems(columns), [columns])
  const columnIds = useMemo(() => columnItems.map((item) => item.id), [columnItems])
  const columnStorageKey = columnSettingsKey
    ? `${COLUMN_SETTINGS_STORAGE_PREFIX}${columnSettingsKey}`
    : undefined
  const [columnSettings, setColumnSettings] = useState<ColumnSettings>(() =>
    readColumnSettings(columnStorageKey, createColumnItems(columns).map((item) => item.id)),
  )
  const [draggingColumnId, setDraggingColumnId] = useState<string | null>(null)

  const tableScrollY = useMemo(() => {
    if (tableWrapperHeight <= 0) return undefined
    return Math.max(tableWrapperHeight - TABLE_SCROLL_OFFSET, MIN_TABLE_SCROLL_Y)
  }, [tableWrapperHeight])

  const commitColumnSettings = useCallback((nextSettings: ColumnSettings) => {
    const normalized = normalizeColumnSettings(nextSettings, columnIds)
    setColumnSettings(normalized)
    writeColumnSettings(columnStorageKey, normalized)
  }, [columnIds, columnStorageKey])

  const orderedColumnItems = useMemo(() => {
    const orderIndex = new Map(columnSettings.order.map((id, index) => [id, index]))
    return [...columnItems].sort((left, right) => {
      const leftOrder = orderIndex.get(left.id) ?? left.index + columnItems.length
      const rightOrder = orderIndex.get(right.id) ?? right.index + columnItems.length
      return leftOrder - rightOrder
    })
  }, [columnItems, columnSettings.order])

  const visibleColumns = useMemo(() => {
    const hidden = new Set(columnSettings.hidden)
    return orderedColumnItems.filter((item) => !hidden.has(item.id)).map((item) => item.column)
  }, [columnSettings.hidden, orderedColumnItems])

  const toggleColumnVisible = useCallback((id: string, visible: boolean) => {
    const hidden = visible
      ? columnSettings.hidden.filter((hiddenId) => hiddenId !== id)
      : [...columnSettings.hidden, id]
    commitColumnSettings({ ...columnSettings, hidden })
  }, [columnSettings, commitColumnSettings])

  const moveColumn = useCallback((sourceId: string, targetId: string) => {
    if (sourceId === targetId) return
    const nextOrder = orderedColumnItems.map((item) => item.id)
    const sourceIndex = nextOrder.indexOf(sourceId)
    const targetIndex = nextOrder.indexOf(targetId)
    if (sourceIndex === -1 || targetIndex === -1) return

    nextOrder.splice(sourceIndex, 1)
    nextOrder.splice(targetIndex, 0, sourceId)
    commitColumnSettings({ ...columnSettings, order: nextOrder })
  }, [columnSettings, commitColumnSettings, orderedColumnItems])

  const resetColumnSettings = useCallback(() => {
    commitColumnSettings(normalizeColumnSettings({ order: columnIds, hidden: [] }, columnIds))
  }, [columnIds, commitColumnSettings])

  const columnSettingsContent = columnSettingsKey ? (
    <div className={styles.columnSettingsPanel}>
      <div className={styles.columnSettingsHeader}>
        <span>列显示</span>
        <Button type="link" size="small" onClick={resetColumnSettings}>
          恢复默认
        </Button>
      </div>
      <div className={styles.columnSettingsList}>
        {orderedColumnItems.map((item) => (
          <div
            key={item.id}
            className={styles.columnSettingsItem}
            draggable
            onDragStart={() => setDraggingColumnId(item.id)}
            onDragEnd={() => setDraggingColumnId(null)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (draggingColumnId) moveColumn(draggingColumnId, item.id)
              setDraggingColumnId(null)
            }}
          >
            <HolderOutlined className={styles.columnSettingsHandle} />
            <Checkbox
              checked={!columnSettings.hidden.includes(item.id)}
              onChange={(event) => toggleColumnVisible(item.id, event.target.checked)}
            >
              {item.label}
            </Checkbox>
          </div>
        ))}
      </div>
    </div>
  ) : null

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
            {columnSettingsKey && (
              <Popover
                content={columnSettingsContent}
                placement="bottomRight"
                trigger="click"
              >
                <Tooltip title="列设置">
                  <Button
                    aria-label="列设置"
                    type="text"
                    icon={<SettingOutlined />}
                  />
                </Tooltip>
              </Popover>
            )}
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
            columns={columnSettingsKey ? visibleColumns : columns}
            dataSource={dataSource}
            loading={loading}
            pagination={pagination}
            rowSelection={rowSelection}
            expandable={expandable}
            tableLayout="fixed"
            scroll={{ y: tableScrollY }}
            {...tableProps}
          />
        </div>
      </Card>
    </div>
  )
}
