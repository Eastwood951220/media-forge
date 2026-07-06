import { Alert, Card, Descriptions, Tag } from 'antd'
import type { StorageTestResult } from '@/api/storage/storageConfig'
import styles from '../StorageConfigPage.module.less'

export default function TestResultCard({ result }: { result: StorageTestResult }) {
  const items = [
    { label: 'gRPC 连接', value: result.grpc_reachable, error: result.grpc_error },
    { label: 'API 授权', value: result.api_authorized, error: result.api_error },
    { label: '下载目录', value: result.download_root_exists, error: result.download_root_error },
    { label: '目标文件夹', value: result.target_folder_accessible, error: result.target_folder_error },
  ]
  const failedItems = items.filter((item) => !item.value && item.error)
  const allPassed = items.every((item) => item.value)

  return (
    <Card title="测试结果" className={styles.resultCard} size="small">
      <Descriptions column={2} size="small">
        {items.map((item) => (
          <Descriptions.Item key={item.label} label={item.label}>
            <Tag color={item.value ? 'success' : 'error'}>{item.value ? '通过' : '失败'}</Tag>
          </Descriptions.Item>
        ))}
      </Descriptions>

      {failedItems.length > 0 && (
        <Alert
          type="error"
          message="错误详情"
          description={
            <ul>
              {failedItems.map((item) => (
                <li key={item.label}>
                  {item.label}: {item.error}
                </li>
              ))}
            </ul>
          }
          showIcon
        />
      )}

      {allPassed && <Alert type="success" message="所有测试通过" showIcon />}
    </Card>
  )
}
