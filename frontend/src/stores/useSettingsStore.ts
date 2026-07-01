import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type SettingsState = {
  showSettings: boolean
  showTagsView: true
  showSidebarLogo: boolean
  fixedHeader: boolean
  showSettingsDrawer: boolean
  showThemeModeToggle: boolean
  openSidebarOnDesktop: boolean
  setShowSettings: (show: boolean) => void
  toggleTagsView: () => void
  toggleSidebarLogo: () => void
  toggleFixedHeader: () => void
  setShowSettingsDrawer: (show: boolean) => void
}

export const useSettingsStore = create<SettingsState>()(
  devtools(
    persist(
      (set) => ({
        showSettings: false,
        showTagsView: true as const,
        showSidebarLogo: true,
        fixedHeader: true,
        showSettingsDrawer: false,
        showThemeModeToggle: true,
        openSidebarOnDesktop: true,

        setShowSettings: (showSettings) => set({ showSettings }),
        toggleTagsView: () => set({ showTagsView: true as const }),
        toggleSidebarLogo: () => set((state) => ({ showSidebarLogo: !state.showSidebarLogo })),
        toggleFixedHeader: () => set((state) => ({ fixedHeader: !state.fixedHeader })),
        setShowSettingsDrawer: (showSettingsDrawer) => set({ showSettingsDrawer }),
      }),
      {
        name: 'media-forge-settings',
      },
    ),
  ),
)
