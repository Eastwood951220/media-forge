import type { ColumnsType, TablePaginationConfig, TableProps } from 'antd/es/table'
import type { ReactNode } from 'react'

export interface BaseListPageProps<T extends object> {
  rowKey: TableProps<T>['rowKey']
  columns: ColumnsType<T>
  dataSource: T[]
  loading?: boolean
  pagination?: false | TablePaginationConfig
  rowSelection?: TableProps<T>['rowSelection']
  queryNode?: ReactNode
  toolbarLeft?: ReactNode
  tableProps?: Omit<TableProps<T>, 'rowKey' | 'columns' | 'dataSource' | 'loading' | 'pagination' | 'rowSelection' | 'expandable'>
  expandable?: TableProps<T>['expandable']
  onRefresh?: () => void
  queryVisibleDefault?: boolean
}
