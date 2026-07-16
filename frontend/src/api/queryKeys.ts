export const queryKeys = {
  dashboard: {
    overview: () => ['dashboard', 'overview'] as const,
  },
  crawlerRuns: {
    list: (params: { page: number; size: number; task_id?: string; status?: string }) =>
      ['crawlerRuns', params] as const,
    count: (params: { task_id?: string; status?: string }) =>
      ['crawlerRuns', 'count', params] as const,
  },
  crawlerTasks: {
    list: (params: { page: number; size: number; keyword?: string }) =>
      ['crawlerTasks', params] as const,
    count: (params: { keyword?: string }) =>
      ['crawlerTasks', 'count', params] as const,
    runtimeStatuses: () => ['crawlerTaskRuntimeStatuses'] as const,
  },
  movies: {
    list: (params: Record<string, unknown>) => ['movies', params] as const,
  },
  storageTasks: {
    list: (params: { page: number; size: number; status?: string; keyword?: string }) =>
      ['storageTasks', params] as const,
    count: (params: { status?: string; keyword?: string }) =>
      ['storageTasks', 'count', params] as const,
    subtasks: (mainTaskId: string, params: { page?: number; limit?: number }) =>
      ['storageSubtasks', mainTaskId, params] as const,
  },
} as const
