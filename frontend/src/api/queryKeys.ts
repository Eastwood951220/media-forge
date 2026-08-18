export const queryKeys = {
  dashboard: {
    overview: () => ['dashboard', 'overview'] as const,
  },
  crawlerAgent: {
    all: () => ['crawlerAgent'] as const,
    status: () => ['crawlerAgent', 'status'] as const,
    events: (params: Record<string, unknown> = {}) =>
      ['crawlerAgent', 'events', params] as const,
  },
  crawlerRunAgent: {
    all: (runId: string) => ['crawlerRunAgent', runId] as const,
    workItems: (runId: string) => ['crawlerRunAgent', runId, 'workItems'] as const,
    events: (runId: string, params: Record<string, unknown> = {}) =>
      ['crawlerRunAgent', runId, 'events', params] as const,
  },
  crawlerRuns: {
    all: () => ['crawlerRuns'] as const,
    list: (params: { page: number; size: number; task_id?: string; status?: string }) =>
      ['crawlerRuns', params] as const,
  },
  crawlerTasks: {
    all: () => ['crawlerTasks'] as const,
    list: (params: { page: number; size: number; keyword?: string }) =>
      ['crawlerTasks', params] as const,
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
