import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

export type TagView = {
  path: string
  fullPath: string
  title: string
  query?: Record<string, unknown>
  closable?: boolean
}

const DASHBOARD_TAG: TagView = {
  path: '/',
  fullPath: '/',
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

function normalizeViews(views: TagView[]): TagView[] {
  const withDashboard = views.some((view) => view.fullPath === DASHBOARD_TAG.fullPath)
    ? views
    : [DASHBOARD_TAG, ...views]
  return withDashboard.length > 0 ? withDashboard : [DASHBOARD_TAG]
}

export const useTagsViewStore = create<TagsViewState>()(
  devtools(
    persist(
      (set, get) => ({
        visitedViews: [DASHBOARD_TAG],

        addVisitedView: (view) => {
          const { visitedViews } = get()
          if (visitedViews.some((item) => item.fullPath === view.fullPath)) {
            get().updateVisitedView(view)
            return
          }

          set({ visitedViews: normalizeViews([...visitedViews, view]) })
        },

        updateVisitedView: (view) => {
          const { visitedViews } = get()
          set({
            visitedViews: normalizeViews(
              visitedViews.map((item) =>
                item.fullPath === view.fullPath ? { ...item, ...view } : item,
              ),
            ),
          })
        },

        removeSelectedView: (view) => {
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => item.fullPath !== view.fullPath || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeOtherViews: (view) => {
          const nextViews = normalizeViews(
            get().visitedViews.filter(
              (item) => item.fullPath === view.fullPath || item.closable === false,
            ),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeLeftViews: (view) => {
          const { visitedViews } = get()
          const targetIndex = visitedViews.findIndex((item) => item.fullPath === view.fullPath)
          if (targetIndex <= 0) return visitedViews

          const nextViews = normalizeViews(
            visitedViews.filter((item, index) => index >= targetIndex || item.closable === false),
          )
          set({ visitedViews: nextViews })
          return nextViews
        },

        removeRightViews: (view) => {
          const { visitedViews } = get()
          const targetIndex = visitedViews.findIndex((item) => item.fullPath === view.fullPath)
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
        partialize: (state) => ({ visitedViews: state.visitedViews }),
      },
    ),
  ),
)
