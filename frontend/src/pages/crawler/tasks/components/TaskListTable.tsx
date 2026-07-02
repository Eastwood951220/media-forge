import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input, Space, Switch, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { CrawlTask } from '@/api/crawlTask/types.ts'
import styles from '../TaskPages.module.less'

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
      render: (name: string) => (
        <Typography.Text strong style={{ fontSize: 14 }}>
          {name}
        </Typography.Text>
      ),
    },
    {
      title: 'URL 数量',
      key: 'url_count',
      width: 110,
      align: 'center',
      render: (_, record) => (
        <Tag color="blue" style={{ margin: 0, borderRadius: 4 }}>
          {record.urls?.length ?? 0} 个 URL
        </Tag>
      ),
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
              <Tag key={`${name}-${index}`} style={{ borderRadius: 4 }}>
                {name}
              </Tag>
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
      align: 'center',
      render: (_, record) => (
        <Switch
          checked={!record.is_skip}
          onChange={() => onToggleSkip(record)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
          style={{
            backgroundColor: !record.is_skip ? '#1e40af' : undefined,
          }}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 130,
      align: 'center',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(record)}
              style={{ color: '#1e40af' }}
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
    showTotal: (count) => `共 ${count} 条`,
    onChange: onPageChange,
  }

  return (
    <div>
      <div className={styles.searchBar}>
        <Input.Search
          placeholder="搜索任务名称"
          allowClear
          enterButton={<SearchOutlined />}
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          onSearch={onSearch}
          style={{ borderRadius: 8 }}
        />
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={tasks}
        loading={loading}
        pagination={pagination}
        rowClassName={(record) => (record.is_skip ? styles.disabledRow : '')}
        style={{ borderRadius: 8 }}
        onRow={(record) => ({
          style: {
            cursor: 'pointer',
            transition: 'background 0.15s ease',
          },
          onClick: (e) => {
            // Avoid triggering row click when clicking buttons/switch
            const target = e.target as HTMLElement
            if (target.closest('.ant-btn') || target.closest('.ant-switch')) return
            onEdit(record)
          },
        })}
      />
    </div>
  )
}

export default TaskListTable
