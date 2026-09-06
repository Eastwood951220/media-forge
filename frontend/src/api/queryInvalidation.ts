import type { QueryClient } from '@tanstack/react-query'
import type { BackupGroup } from './backup/types'
import { queryKeys } from './queryKeys'

export function invalidateCrawlerRunLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerRuns.all() })
}

export function invalidateCrawlerTaskLists(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerTasks.all() })
}

export function invalidateCrawlerSchedules(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.crawlerSchedules.all() })
}

export function invalidateBackupFiles(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.backup.files() })
}

export function invalidateBackupConfig(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: queryKeys.backup.config() })
}

/** Invalidate the state touched by restoring the given backup groups. */
export function invalidateBackupAfterRestore(
  queryClient: QueryClient,
  groups: BackupGroup[],
) {
  void invalidateBackupFiles(queryClient)
  if (groups.includes('movies')) {
    void queryClient.invalidateQueries({ queryKey: ['movies'] })
  }
  if (groups.includes('tasks')) {
    void invalidateCrawlerTaskLists(queryClient)
    void invalidateCrawlerSchedules(queryClient)
  }
  if (groups.includes('config')) {
    void queryClient.invalidateQueries({ queryKey: ['crawlerConfig'] })
    void queryClient.invalidateQueries({ queryKey: ['storageConfig'] })
    void queryClient.invalidateQueries({ queryKey: ['movieFilterConfig'] })
  }
}
