import { Modal } from 'antd'

export function confirmRetryTask(detailId: string, onRetryTask: (detailId: string) => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取失败子任务',
    content: '确认重新爬取该失败子任务？',
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetryTask(detailId)
      onDone()
    },
  })
}

export function confirmRetrySelected(detailIds: string[], onRetrySelected: (detailIds: string[]) => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取选中项',
    content: `确认重新爬取选中的 ${detailIds.length} 个失败子任务？`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetrySelected(detailIds)
      onDone()
    },
  })
}

export function confirmRetryAllFailed(failedCount: number, onRetryAllFailed: () => Promise<void>, onDone: () => void) {
  Modal.confirm({
    title: '重新爬取全部失败',
    content: `确认重新爬取全部 ${failedCount} 个失败子任务？`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await onRetryAllFailed()
      onDone()
    },
  })
}
