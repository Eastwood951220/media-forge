import { Card, Input, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { CrawlRunDetailTask } from '@/api/crawlerRun/types'
import { runDetailStatusLabels } from '../utils/status'

interface RunTaskTableProps {
  tasks: CrawlRunDetailTask[]
  loading: boolean
  statusFilter: string | undefined
  keyword: string
  pageSize: number
  onStatusChange: (value: string | undefined) => void
  onKeywordSearch: (value: string) => void
  onPageSizeChange: (size: number) => void
}

const columns: ColumnsType<CrawlRunDetailTask> = [
  {
    title: '番号',
    dataIndex: 'code',
    key: 'code',
    width: 120,
  },
  {
    title: '来源',
    dataIndex: 'source_name',
    key: 'source_name',
    ellipsis: true,
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
    render: (status: string) => {
      const { text, color } = runDetailStatusLabels[status] || { text: status, color: 'default' }
      return <Tag color={color}>{text}</Tag>
    },
  },
  {
    title: '错误',
    dataIndex: 'error',
    key: 'error',
    ellipsis: true,
  },
]

function RunTaskTable({
  tasks,
  loading,
  statusFilter,
  keyword,
  pageSize,
  onStatusChange,
  onKeywordSearch,
  onPageSizeChange,
}: RunTaskTableProps) {
  return (
    <Card title="子任务列表">
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 120 }}
          value={statusFilter}
          onChange={(value) => onStatusChange(value)}
          options={Object.entries(runDetailStatusLabels).map(([key, { text }]) => ({
            value: key,
            label: text,
          }))}
        />
        <Input.Search
          placeholder="搜索番号或名称"
          allowClear
          value={keyword}
          onSearch={(value) => onKeywordSearch(value)}
          style={{ width: 200 }}
        />
      </Space>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={{
          pageSize,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100', '200'],
          onChange: (_page, size) => onPageSizeChange(size),
        }}
      />
    </Card>
  )
}

export default RunTaskTable
