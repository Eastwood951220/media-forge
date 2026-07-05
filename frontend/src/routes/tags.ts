export type RouteTagMeta = {
  title: string
  affix?: boolean
  activeMenu?: string
  singletonKey?: string
}

const ROUTE_TAGS: Array<{ pattern: RegExp; meta: RouteTagMeta }> = [
  { pattern: /^\/$/, meta: { title: '仪表盘', affix: true } },
  { pattern: /^\/crawler\/tasks$/, meta: { title: '任务列表' } },
  { pattern: /^\/crawler\/config$/, meta: { title: '爬虫配置' } },
  {
    pattern: /^\/crawler\/tasks\/new$/,
    meta: { title: '新建任务', activeMenu: '/crawler/tasks' },
  },
  {
    pattern: /^\/crawler\/tasks\/[^/]+\/edit$/,
    meta: {
      title: '编辑任务',
      activeMenu: '/crawler/tasks',
      singletonKey: '/crawler/tasks/:id/edit',
    },
  },
  { pattern: /^\/crawler\/runs$/, meta: { title: '运行记录', activeMenu: '/crawler/runs' } },
  {
    pattern: /^\/crawler\/runs\/[^/]+$/,
    meta: {
      title: '运行详情',
      activeMenu: '/crawler/runs',
      singletonKey: '/crawler/runs/:id',
    },
  },
  { pattern: /^\/content\/movies$/, meta: { title: '影片列表' } },
  { pattern: /^\/storage\/config$/, meta: { title: '存储配置' } },
  { pattern: /^\/storage\/tasks$/, meta: { title: '存储任务' } },
  {
    pattern: /^\/storage\/tasks\/[^/]+$/,
    meta: {
      title: '存储任务详情',
      activeMenu: '/storage/tasks',
      singletonKey: '/storage/tasks/:id',
    },
  },
  {
    pattern: /^\/storage\/tasks\/subtasks\/[^/]+$/,
    meta: {
      title: '子任务详情',
      activeMenu: '/storage/tasks',
      singletonKey: '/storage/tasks/subtasks/:id',
    },
  },
]

export function getRouteTagMeta(pathname: string): RouteTagMeta {
  return ROUTE_TAGS.find((item) => item.pattern.test(pathname))?.meta ?? {
    title: pathname,
  }
}

export function getFullPath(pathname: string, searchStr: string): string {
  return `${pathname}${searchStr || ''}`
}

export function getRouteViewKey(pathname: string, searchStr: string): string {
  return getRouteTagMeta(pathname).singletonKey ?? getFullPath(pathname, searchStr)
}
