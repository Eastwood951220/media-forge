import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type ThemeMode = 'light' | 'dark'

type ThemeState = {
  mode: ThemeMode
  darkMode: boolean
  primaryColor: string
  setMode: (mode: ThemeMode) => void
  setDarkMode: (darkMode: boolean) => void
  toggleMode: () => void
  setPrimaryColor: (color: string) => void
}

export const useThemeStore = create<ThemeState>()(
  devtools(
    persist(
      (set) => ({
        mode: 'light',
        darkMode: false,
        primaryColor: '#006AFF',

        setMode: (mode) =>
          set({
            mode,
            darkMode: mode === 'dark',
          }),

        setDarkMode: (darkMode) =>
          set({
            darkMode,
            mode: darkMode ? 'dark' : 'light',
          }),

        toggleMode: () =>
          set((state) => {
            const nextMode = state.darkMode ? 'light' : 'dark'
            return {
              mode: nextMode,
              darkMode: nextMode === 'dark',
            }
          }),

        setPrimaryColor: (primaryColor) => set({ primaryColor }),
      }),
      {
        name: 'media-forge-theme',
      },
    ),
  ),
)
