import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'

type ImageBlurState = {
  enabled: boolean
  setEnabled: (enabled: boolean) => void
  toggle: () => void
}

export const useImageBlurStore = create<ImageBlurState>()(
  devtools(
    persist(
      (set) => ({
        enabled: true,
        setEnabled: (enabled) => set({ enabled }),
        toggle: () => set((state) => ({ enabled: !state.enabled })),
      }),
      {
        name: 'media-forge-image-blur',
      },
    ),
  ),
)
