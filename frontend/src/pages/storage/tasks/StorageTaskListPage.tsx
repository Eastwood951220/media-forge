import { StorageMainTaskTable } from './components/StorageMainTaskTable'
import { useStorageTaskList } from './hooks/useStorageTaskList'
import styles from './StorageTasks.module.less'

function StorageTaskListPage() {
  const list = useStorageTaskList()

  return (
    <div className={styles.page}>
      <StorageMainTaskTable
        current={list.current}
        loading={list.loading}
        onDelete={list.handleDelete}
        onPageChange={list.setCurrent}
        onPageSizeChange={list.setPageSize}
        onRefresh={list.refreshCurrentPage}
        onRestart={list.handleRestart}
        onStop={list.handleStop}
        pageSize={list.pageSize}
        tasks={list.tasks}
        total={list.total}
        hasMore={list.hasMore}
        countLoading={list.countLoading}
      />
    </div>
  )
}

export default StorageTaskListPage
