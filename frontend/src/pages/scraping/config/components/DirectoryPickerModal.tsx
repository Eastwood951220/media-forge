import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Empty, Modal, Space, Switch, Typography } from 'antd'
import { ArrowUpOutlined, FolderOutlined } from '@ant-design/icons'
import {
  listScrapingDirectories,
  type ScrapingDirectoryListing,
} from '@/api/scraping/scrapingConfig'
import { getErrorMessage } from '../utils/error'
import styles from './DirectoryPickerModal.module.less'

interface DirectoryPickerModalProps {
  open: boolean
  initialPath?: string
  onCancel: () => void
  onSelect: (path: string) => void
}

export default function DirectoryPickerModal({
  open,
  initialPath,
  onCancel,
  onSelect,
}: DirectoryPickerModalProps) {
  const [listing, setListing] = useState<ScrapingDirectoryListing | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [includeHidden, setIncludeHidden] = useState(false)

  const loadDirectory = useCallback(async (path: string | undefined, hidden: boolean) => {
    setLoading(true)
    setError('')
    try {
      setListing(await listScrapingDirectories(path, hidden))
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  const openPicker = useCallback(async () => {
    setIncludeHidden(false)
    setLoading(true)
    setError('')
    try {
      setListing(await listScrapingDirectories(initialPath, false))
    } catch (loadError: unknown) {
      const reason = getErrorMessage(loadError)
      try {
        setListing(await listScrapingDirectories(undefined, false))
        setError(`${reason}，已打开默认目录`)
      } catch {
        setError(reason)
      }
    } finally {
      setLoading(false)
    }
  }, [initialPath])

  useEffect(() => {
    if (!open) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Loading the starting folder on open is intentional.
    void openPicker()
  }, [open, openPicker])

  const handleHiddenChange = (checked: boolean) => {
    setIncludeHidden(checked)
    if (listing) void loadDirectory(listing.path, checked)
  }

  const entries = listing?.entries ?? []

  return (
    <Modal
      title="选择文件夹"
      open={open}
      onCancel={onCancel}
      width={600}
      okText="选择当前文件夹"
      cancelText="取消"
      confirmLoading={loading}
      okButtonProps={{
        disabled: listing === null || listing.parent === null,
        title: listing !== null && listing.parent === null ? '不能选择文件系统根目录' : undefined,
      }}
      onOk={() => {
        if (listing) onSelect(listing.path)
      }}
      destroyOnHidden
    >
      <div className={styles.body}>
        <div className={styles.toolbar}>
          <Button
            icon={<ArrowUpOutlined />}
            aria-label="上级目录"
            disabled={!listing?.parent || loading}
            onClick={() => {
              if (listing?.parent) void loadDirectory(listing.parent, includeHidden)
            }}
          >
            上级
          </Button>
          <Typography.Text
            code
            className={styles.path}
            title={listing?.path}
          >
            {listing?.path ?? '加载中…'}
          </Typography.Text>
        </div>

        {listing && listing.roots.length > 0 && (
          <div className={styles.roots}>
            <Typography.Text type="secondary">常用位置</Typography.Text>
            <Space size={[6, 6]} wrap>
              {listing.roots.map((root) => (
                <Button
                  key={root.path}
                  size="small"
                  onClick={() => void loadDirectory(root.path, includeHidden)}
                >
                  {root.path}
                </Button>
              ))}
            </Space>
          </div>
        )}

        <div className={styles.hiddenRow}>
          <Typography.Text type="secondary">显示隐藏文件夹</Typography.Text>
          <Switch
            checked={includeHidden}
            aria-label="显示隐藏文件夹"
            onChange={handleHiddenChange}
          />
        </div>

        {error && <Alert type="error" showIcon title={error} />}

        <div className={styles.entries}>
          {entries.length > 0 ? (
            entries.map((entry) => (
              <Button
                key={entry.path}
                type="text"
                block
                className={styles.entry}
                icon={<FolderOutlined />}
                aria-label={entry.name}
                onClick={() => void loadDirectory(entry.path, includeHidden)}
              >
                <span className={styles.entryName}>{entry.name}</span>
              </Button>
            ))
          ) : (
            !loading && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有子文件夹" />
          )}
        </div>

        {listing?.truncated && (
          <Alert
            type="warning"
            showIcon
            title="文件夹数量过多，仅显示当前目录下的前 500 个文件夹。"
          />
        )}

        <Typography.Text type="secondary" className={styles.hint}>
          列表来自服务端文件系统（Docker 部署时为容器内路径）。需要刮削的目录请先挂载到容器。
        </Typography.Text>
      </div>
    </Modal>
  )
}
