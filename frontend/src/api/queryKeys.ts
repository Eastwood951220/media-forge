export const queryKeys = {
  dashboard: {
    overview: () => ['dashboard', 'overview'] as const,
  },
  crawlerRuns: {
    list: (params: { skip?: number; limit?: number; task_id?: string; status?: string }) =>
      ['crawlerRuns', params] as const,
  },
  crawlerTasks: {
    list: (params: { skip?: number; limit?: number; keyword?: string }) =>
      ['crawlerTasks', params] as const,
    runtimeStatuses: () => ['crawlerTaskRuntimeStatuses'] as const,
  },
  movies: {
    list: (params: Record<string, unknown>) => ['movies', params] as const,
  },
  storageTasks: {
    list: (params: { page?: number; limit?: number; status?: string; keyword?: string }) =>
      ['storageTasks', params] as const,
    subtasks: (mainTaskId: string, params: { page?: number; limit?: number }) =>
      ['storageSubtasks', mainTaskId, params] as const,
  },
} as const
