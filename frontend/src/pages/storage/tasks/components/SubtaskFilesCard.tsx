import { Card, Descriptions, Empty, Tag, Typography } from 'antd'
import type { StorageSubTask } from '@/api/storage/storageTasks/types'
import styles from '../StorageTasks.module.less'

interface SubtaskFilesCardProps {
  subtask: StorageSubTask
}

function stringValue(file: Record<string, unknown>, key: string): string {
  const value = file[key]
  return typeof value === 'string' ? value : ''
}

function stringArrayValue(file: Record<string, unknown>, key: string): string[] {
  const value = file[key]
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : []
}

const skipReasonLabels: Record<string, string> = {
  rename_failed: '重命名失败',
  rename_name_exists: '重命名目标已存在',
  target_exists: '目标已存在',
}

function fileKey(file: Record<string, unknown>, fallback: string): string {
  return (
    stringValue(file, 'moved_path') ||
    stringValue(file, 'renamed_path') ||
    stringValue(file, 'path') ||
    stringValue(file, 'name') ||
    fallback
  )
}

function FilePath({ label, value }: { label: string; value: string }) {
  if (!value) return null
  return (
    <div className={styles.fileMetaRow}>
      <Typography.Text type="secondary" className={styles.fileMetaLabel}>
        {label}
      </Typography.Text>
      <Typography.Text code className={styles.filePath}>
        {value}
      </Typography.Text>
    </div>
  )
}

function FileCard({
  file,
  index,
  type,
}: {
  file: Record<string, unknown>
  index: number
  type: 'moved' | 'skipped'
}) {
  const copiedPaths = stringArrayValue(file, 'copied_paths')
  const skipReason = stringValue(file, 'skip_reason')
  const title = stringValue(file, 'renamed_name') || stringValue(file, 'name') || `文件 ${index + 1}`
  return (
    <div className={styles.fileResultItem}>
      <div className={styles.fileResultHeader}>
        <Typography.Text strong className={styles.fileResultTitle}>
          {title}
        </Typography.Text>
        {type === 'moved' ? (
          <Tag color="green">已移动</Tag>
        ) : (
          <Tag color="orange">{skipReasonLabels[skipReason] || skipReason || '已跳过'}</Tag>
        )}
      </div>
      <div className={styles.fileMetaList}>
        <FilePath label="原路径" value={stringValue(file, 'path')} />
        <FilePath label="重命名后" value={stringValue(file, 'renamed_path')} />
        <FilePath label="移动到" value={stringValue(file, 'moved_path')} />
        {copiedPaths.map((path, copiedIndex) => (
          <FilePath key={path} label={`复制到 ${copiedIndex + 1}`} value={path} />
        ))}
      </div>
    </div>
  )
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
          <div className={styles.fileResultList}>
            {subtask.moved_files.map((file, index) => (
              <FileCard key={fileKey(file, `moved-${index}`)} file={file} index={index} type="moved" />
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无移动文件" />
        )}
      </Card>

      <Card title="跳过的文件" style={{ marginBottom: 16 }}>
        {subtask.skipped_files.length > 0 ? (
          <div className={styles.fileResultList}>
            {subtask.skipped_files.map((file, index) => (
              <FileCard key={fileKey(file, `skipped-${index}`)} file={file} index={index} type="skipped" />
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无跳过文件" />
        )}
      </Card>
    </>
  )
}
