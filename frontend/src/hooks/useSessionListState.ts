import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

function readSessionListState<T extends object>(key: string, initialState: T): T {
  if (typeof window === 'undefined') return initialState

  try {
    const raw = window.sessionStorage.getItem(key)
    if (!raw) return initialState
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return initialState
    return { ...initialState, ...parsed }
  } catch {
    return initialState
  }
}

function writeSessionListState<T extends object>(key: string, state: T) {
  if (typeof window === 'undefined') return

  try {
    window.sessionStorage.setItem(key, JSON.stringify(state))
  } catch {
    // Ignore storage quota/privacy errors; keep-alive still preserves state in memory.
  }
}

export function useSessionListState<T extends object>(
  key: string,
  initialState: T,
): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState(() => readSessionListState(key, initialState))

  useEffect(() => {
    writeSessionListState(key, state)
  }, [key, state])

  return [state, setState]
}
