import { create } from 'zustand'

type TaskListQueryState = {
  keyword: string
  current: number
  setKeyword: (keyword: string) => void
  setCurrent: (current: number) => void
  reset: () => void
}

export const useTaskListQueryStore = create<TaskListQueryState>()((set) => ({
  keyword: '',
  current: 1,
  setKeyword: (keyword) => set({ keyword, current: 1 }),
  setCurrent: (current) => set({ current }),
  reset: () => set({ keyword: '', current: 1 }),
}))
