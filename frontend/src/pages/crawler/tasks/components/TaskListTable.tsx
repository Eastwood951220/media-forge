import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { CrawlTask } from '@/api/crawlTask/types.ts'

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
  onToggleSkip: (task: CrawlTask) => void
  onSearch: (keyword: string) => void
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
  onToggleSkip,
  onSearch,
}: TaskListTableProps) {
  const columns: ColumnsType<CrawlTask> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
    },
    {
      title: 'URL 数量',
      key: 'url_count',
      width: 110,
      render: (_, record) => <Tag>{record.urls?.length ?? 0} 个 URL</Tag>,
    },
    {
      title: 'URL 名称',
      key: 'url_names',
      width: 280,
      render: (_, record) => {
        const names = record.urls?.filter((url) => url.url_name).map((url) => url.url_name) ?? []
        if (names.length === 0) return <Typography.Text type="secondary">-</Typography.Text>
        return (
          <Space size={4} wrap>
            {names.map((name, index) => (
              <Tag key={`${name}-${index}`}>{name}</Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'is_skip',
      key: 'is_skip',
      width: 100,
      render: (_, record) => (
        <Switch
          checked={!record.is_skip}
          onChange={() => onToggleSkip(record)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button type="text" size="small" icon={<EditOutlined />} onClick={() => onEdit(record)} />
          </Tooltip>
          <Tooltip title="删除">
            <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(record)} />
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
    showTotal: (count) => `共 ${count} 条`,
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
      <Table rowKey="id" columns={columns} dataSource={tasks} loading={loading} pagination={pagination} />
    </div>
  )
}

export default TaskListTable
