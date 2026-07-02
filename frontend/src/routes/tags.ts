export type RouteTagMeta = {
  title: string
  affix?: boolean
  activeMenu?: string
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
    meta: { title: '编辑任务', activeMenu: '/crawler/tasks' },
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
