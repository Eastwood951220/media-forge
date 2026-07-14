import { Button, Input, Select } from 'antd'
import styles from '../RunDetailPage.module.less'
import { runDetailStatusLabels } from '../utils/status'

interface RunTaskToolbarProps {
  statusFilter: string | undefined
  keyword: string
  retryEnabled: boolean
  selectedFailedCount: number
  failedCount: number
  actionLoading: 'stop' | 'restart' | 'retry' | null
  onStatusChange: (value: string | undefined) => void
  onKeywordSearch: (value: string) => void
  onRetrySelected: () => void
  onRetryAllFailed: () => void
}

function RunTaskToolbar({
  statusFilter,
  keyword,
  retryEnabled,
  selectedFailedCount,
  failedCount,
  actionLoading,
  onStatusChange,
  onKeywordSearch,
  onRetrySelected,
  onRetryAllFailed,
}: RunTaskToolbarProps) {
  return (
    <div className={styles.filterSection}>
      <div className={styles.filterControls}>
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
      </div>
      <div className={styles.filterActions}>
        {retryEnabled && selectedFailedCount > 0 && (
          <Button loading={actionLoading === 'retry'} onClick={onRetrySelected}>
            重新爬取选中项 ({selectedFailedCount})
          </Button>
        )}
        {retryEnabled && failedCount > 0 && (
          <Button
            type="primary"
            danger
            loading={actionLoading === 'retry'}
            onClick={onRetryAllFailed}
          >
            重新爬取全部失败 ({failedCount})
          </Button>
        )}
      </div>
    </div>
  )
}

export default RunTaskToolbar
