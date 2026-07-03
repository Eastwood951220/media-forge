import { create } from 'zustand'

type TaskListQueryState = {
  keyword: string
  setKeyword: (keyword: string) => void
  reset: () => void
}

export const useTaskListQueryStore = create<TaskListQueryState>()((set) => ({
  keyword: '',
  setKeyword: (keyword) => set({ keyword }),
  reset: () => set({ keyword: '' }),
}))
