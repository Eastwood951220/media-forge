import { Button, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { CrawlRunDetailTask } from '@/api/crawlerRun/types'
import { runDetailStatusLabels } from '../utils/status'

interface CreateRunTaskColumnsArgs {
  retryEnabled: boolean
  actionLoading: 'stop' | 'restart' | 'retry' | null
  onRetryTask: (detailId: string) => void
}

export function createRunTaskColumns({
  retryEnabled,
  actionLoading,
  onRetryTask,
}: CreateRunTaskColumnsArgs): ColumnsType<CrawlRunDetailTask> {
  return [
    {
      title: '番号',
      dataIndex: 'code',
      key: 'code',
      width: 120,
      render: (_, record) => record.display_code || record.code || '-',
    },
    {
      title: '来源',
      dataIndex: 'source_name',
      key: 'source_name',
      ellipsis: true,
      render: (_, record) => record.display_source_name || record.source_name || '-',
    },
    {
      title: 'URL来源',
      dataIndex: 'source_url_name',
      key: 'source_url_name',
      width: 140,
      ellipsis: true,
      render: (_, record) => record.source_url_name || record.task_url_type || '-',
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
    { title: '错误', dataIndex: 'error', key: 'error', ellipsis: true },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) =>
        retryEnabled && record.status === 'crawl_failed' ? (
          <Button
            type="link"
            size="small"
            loading={actionLoading === 'retry'}
            onClick={() => onRetryTask(record.id)}
          >
            重新爬取
          </Button>
        ) : null,
    },
  ]
}
