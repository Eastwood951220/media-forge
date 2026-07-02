import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Space, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { CrawlTask } from '@/api/crawlTask/types'

type TaskListTableProps = {
  tasks: CrawlTask[]
  loading: boolean
  total: number
  current: number
  pageSize: number
  keyword: string
  onKeywordChange: (keyword: string) => void
  onPageChange: (page: number, pageSize: number) => void
  onEdit: (task: CrawlTask) => void
  onDelete: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  pending: { color: 'default', label: '待执行' },
  running: { color: 'processing', label: '运行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

function renderStatus(status: string) {
  const config = STATUS_CONFIG[status] ?? { color: 'default', label: status }
  return <Tag color={config.color}>{config.label}</Tag>
}

function TaskListTable({
  tasks,
  loading,
  total,
  current,
  pageSize,
  keyword,
  onKeywordChange,
  onPageChange,
  onEdit,
  onDelete,
  onSearch,
}: TaskListTableProps) {
  const columns: ColumnsType<CrawlTask> = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: renderStatus,
    },
    {
      title: '关键词',
      dataIndex: 'keywords',
      key: 'keywords',
      width: 200,
      ellipsis: true,
      render: (keywords: string[]) => (
        <span>{keywords.join(', ')}</span>
      ),
    },
    {
      title: '目标网站',
      dataIndex: 'target_websites',
      key: 'target_websites',
      width: 200,
      ellipsis: true,
      render: (sites: string[]) => (
        <span>{sites.length} 个网站</span>
      ),
    },
    {
      title: '最大页数',
      dataIndex: 'max_pages',
      key: 'max_pages',
      width: 100,
    },
    {
      title: '爬取深度',
      dataIndex: 'crawl_depth',
      key: 'crawl_depth',
      width: 100,
    },
    {
      title: '已找到',
      dataIndex: 'total_found',
      key: 'total_found',
      width: 100,
    },
    {
      title: '符合条件',
      dataIndex: 'total_qualified',
      key: 'total_qualified',
      width: 100,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(record)}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => onDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const pagination: TablePaginationConfig = {
    current,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (t) => `共 ${t} 条`,
    onChange: onPageChange,
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          style={{ maxWidth: 320 }}
        />
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={pagination}
      />
    </div>
  )
}

export default TaskListTable
