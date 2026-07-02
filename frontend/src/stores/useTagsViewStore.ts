import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export type TagView = {
  path: string
  fullPath: string
  cacheKey: string
  title: string
  query?: Record<string, unknown>
  closable?: boolean
}

const DASHBOARD_TAG: TagView = {
  path: '/',
  fullPath: '/',
  cacheKey: '/',
  title: '仪表盘',
  closable: false,
}

type TagsViewState = {
  visitedViews: TagView[]
  addVisitedView: (view: TagView) => void
  updateVisitedView: (view: TagView) => void
  removeSelectedView: (view: TagView) => TagView[]
  removeOtherViews: (view: TagView) => TagView[]
  removeLeftViews: (view: TagView) => TagView[]
  removeRightViews: (view: TagView) => TagView[]
  removeAllViews: () => TagView[]
  resetViews: () => void
}

function getTagKey(view: TagView): string {
  return view.cacheKey || view.fullPath
}

function hydrateView(view: TagView): TagView {
  return {
    ...view,
    cacheKey: view.cacheKey || view.fullPath,
  }
}

function normalizeViews(views: TagView[]): TagView[] {
  const normalized: TagView[] = []
  const indexes = new Map<string, number>()

  for (const rawView of views) {
    const view = hydrateView(rawView)
    const key = getTagKey(view)
    const index = indexes.get(key)
    if (index === undefined) {
      indexes.set(key, normalized.length)
      normalized.push(view)
    } else {
      normalized[index] = { ...normalized[index], ...view }
    }
  }

  const dashboardIndex = normalized.findIndex((view) => getTagKey(view) === DASHBOARD_TAG.cacheKey)
  if (dashboardIndex === -1) {
    return [DASHBOARD_TAG, ...normalized]
  }

  const dashboard = { ...DASHBOARD_TAG, ...normalized[dashboardIndex], closable: false }
  const withoutDashboard = normalized.filter((_, index) => index !== dashboardIndex)
  return [dashboard, ...withoutDashboard]
}

export const useTagsViewStore = create<TagsViewState>()(
  devtools(
    persist(
      (set, get) => ({
        visitedViews: [DASHBOARD_TAG],

        addVisitedView: (view) => {
          const normalizedView = hydrateView(view)
          const viewKey = getTagKey(normalizedView)
          const { visitedViews } = get()
          if (visitedViews.some((item) => getTagKey(item) === viewKey)) {
            get().updateVisitedView(normalizedView)
            return
          }

          set({ visitedViews: normalizeViews([...visitedViews, normalizedView]) })
        },

        updateVisitedView: (view) => {
          const normalizedView = hydrateView(view)
          const viewKey = getTagKey(normalizedView)
          const { visitedViews } = get()
          set({
            visitedViews: normalizeViews(
              visitedViews.map((item) =>
                getTagKey(item) === viewKey ? { ...item, ...normalizedView } : item,
              ),
            ),
          })
        },

        removeSelectedView: (view) => {
          const viewKey = getTagKey(hydrateView(view))
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => getTagKey(item) !== viewKey || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeOtherViews: (view) => {
          const viewKey = getTagKey(hydrateView(view))
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => getTagKey(item) === viewKey || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeLeftViews: (view) => {
          const { visitedViews } = get()
          const viewKey = getTagKey(hydrateView(view))
          const targetIndex = visitedViews.findIndex((item) => getTagKey(item) === viewKey)
          if (targetIndex <= 0) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index >= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeRightViews: (view) => {
          const { visitedViews } = get()
          const viewKey = getTagKey(hydrateView(view))
          const targetIndex = visitedViews.findIndex((item) => getTagKey(item) === viewKey)
          if (targetIndex === -1) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index <= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeAllViews: () => {
          const nextViews = normalizeViews(
            get().visitedViews.filter((item) => item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        resetViews: () => {
          set({ visitedViews: [DASHBOARD_TAG] })
        },
      }),
      {
        name: 'media-forge-tags-view',
        partialize: (state) => ({ visitedViews: normalizeViews(state.visitedViews) }),
      },
    ),
  ),
)
