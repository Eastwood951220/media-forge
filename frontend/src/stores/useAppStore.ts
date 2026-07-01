import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type DeviceType = 'desktop' | 'mobile'

type AppState = {
  sidebarCollapsed: boolean
  device: DeviceType
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setDevice: (device: DeviceType) => void
}

export const useAppStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        sidebarCollapsed: false,
        device: 'desktop',

        toggleSidebar: () =>
          set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

        setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),

        setDevice: (device) => set({ device }),
      }),
      {
        name: 'media-forge-app',
        partialize: (state) => ({ sidebarCollapsed: state.sidebarCollapsed }),
      },
    ),
  ),
)
