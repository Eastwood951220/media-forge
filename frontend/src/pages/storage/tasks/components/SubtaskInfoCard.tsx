import { Card, Descriptions, Tag, Typography } from 'antd'
import type { StorageSubTask } from '@/api/storage/storageTasks/types'
import { statusLabels } from '../utils/subtaskStatus'

interface SubtaskInfoCardProps {
  subtask: StorageSubTask
  loading: boolean
}

export function SubtaskInfoCard({ subtask, loading }: SubtaskInfoCardProps) {
  return (
    <Card title="基本信息" style={{ marginBottom: 16 }} loading={loading}>
      <Descriptions column={2}>
        <Descriptions.Item label="番号">{subtask.movie_code}</Descriptions.Item>
        <Descriptions.Item label="标题">{subtask.movie_title || '-'}</Descriptions.Item>
        <Descriptions.Item label="状态">
          <Tag color={statusLabels[subtask.status]?.color}>
            {statusLabels[subtask.status]?.text || subtask.status}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="步骤">{subtask.step || '-'}</Descriptions.Item>
        <Descriptions.Item label="存储模式">{subtask.storage_mode || '-'}</Descriptions.Item>
        <Descriptions.Item label="选择的存储位置">
          {subtask.selected_storage_location || '-'}
        </Descriptions.Item>
        {subtask.skip_reason && (
          <Descriptions.Item label="跳过原因" span={2}>
            {subtask.skip_reason}
          </Descriptions.Item>
        )}
        {subtask.error_message && (
          <Descriptions.Item label="错误信息" span={2}>
            <Typography.Text type="danger">{subtask.error_message}</Typography.Text>
          </Descriptions.Item>
        )}
      </Descriptions>
    </Card>
  )
}
