import { Card, Descriptions, Empty } from 'antd'
import type { StorageSubTask } from '@/api/storage/storageTasks/types'

interface SubtaskFilesCardProps {
  subtask: StorageSubTask
}

export function SubtaskFilesCard({ subtask }: SubtaskFilesCardProps) {
  return (
    <>
      <Card title="目标位置" style={{ marginBottom: 16 }}>
        {subtask.target_locations.length > 0 ? (
          <Descriptions column={1}>
            {subtask.target_locations.map((loc, index) => (
              <Descriptions.Item key={loc} label={`位置 ${index + 1}`}>
                {loc}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无目标位置" />
        )}
      </Card>

      <Card title="移动的文件" style={{ marginBottom: 16 }}>
        {subtask.moved_files.length > 0 ? (
          <Descriptions column={1}>
            {subtask.moved_files.map((file, index) => (
              <Descriptions.Item key={index} label={`文件 ${index + 1}`}>
                {JSON.stringify(file)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无移动文件" />
        )}
      </Card>

      <Card title="跳过的文件" style={{ marginBottom: 16 }}>
        {subtask.skipped_files.length > 0 ? (
          <Descriptions column={1}>
            {subtask.skipped_files.map((file, index) => (
              <Descriptions.Item key={index} label={`文件 ${index + 1}`}>
                {JSON.stringify(file)}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无跳过文件" />
        )}
      </Card>
    </>
  )
}
