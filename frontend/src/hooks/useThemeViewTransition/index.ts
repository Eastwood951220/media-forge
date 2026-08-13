import { useCallback, useRef } from 'react'
import { flushSync } from 'react-dom'
import { useThemeStore } from '@/stores/useThemeStore'
import type { StartViewTransition, UseThemeViewTransitionOptions } from './types'

const DEFAULT_DURATION = 280
const DEFAULT_EASING = 'linear'
const TRANSITION_CLASS = 'theme-transition-active'
const TRANSITION_X = '--theme-transition-x'
const TRANSITION_Y = '--theme-transition-y'
const TRANSITION_RADIUS = '--theme-transition-radius'
const TRANSITION_DURATION = '--theme-transition-duration'
const TRANSITION_EASING = '--theme-transition-easing'
const TOP_RIGHT_ORIGIN_INSET = 44

function shouldSkipTransition(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return true
  }
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function getStartViewTransition(): StartViewTransition | null {
  if (typeof document === 'undefined') {
    return null
  }
  const doc = document as Document & { startViewTransition?: StartViewTransition }
  const fn = doc.startViewTransition
  return typeof fn === 'function' ? fn.bind(doc) : null
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function getTransitionOrigin(originEl?: HTMLElement | null) {
  if (originEl) {
    const { top, left, width, height } = originEl.getBoundingClientRect()
    return {
      x: left + width / 2,
      y: top + height / 2,
    }
  }

  return {
    x: Math.max(window.innerWidth - TOP_RIGHT_ORIGIN_INSET, 0),
    y: TOP_RIGHT_ORIGIN_INSET,
  }
}

function getCoveringRadius(x: number, y: number) {
  return Math.max(
    Math.hypot(x, y),
    Math.hypot(window.innerWidth - x, y),
    Math.hypot(x, window.innerHeight - y),
    Math.hypot(window.innerWidth - x, window.innerHeight - y),
  )
}

function prepareTransition(root: HTMLElement, originEl: HTMLElement | null, duration: number, easing: string) {
  const { x, y } = getTransitionOrigin(originEl)
  const maxRadius = getCoveringRadius(x, y)

  root.style.setProperty(TRANSITION_X, `${x}px`)
  root.style.setProperty(TRANSITION_Y, `${y}px`)
  root.style.setProperty(TRANSITION_RADIUS, `${maxRadius}px`)
  root.style.setProperty(TRANSITION_DURATION, `${duration}ms`)
  root.style.setProperty(TRANSITION_EASING, easing)
  root.classList.add(TRANSITION_CLASS)
}

function clearPreparedTransition(root: HTMLElement) {
  root.classList.remove(TRANSITION_CLASS)
  root.style.removeProperty(TRANSITION_X)
  root.style.removeProperty(TRANSITION_Y)
  root.style.removeProperty(TRANSITION_RADIUS)
  root.style.removeProperty(TRANSITION_DURATION)
  root.style.removeProperty(TRANSITION_EASING)
}

export function useThemeViewTransition({
  duration = DEFAULT_DURATION,
  easing = DEFAULT_EASING,
  toggleTheme,
}: UseThemeViewTransitionOptions) {
  const transitionLockRef = useRef(false)
  const triggerRef = useRef<HTMLElement | null>(null)

  const runTransition = useCallback(async (originEl?: HTMLElement | null) => {
    if (transitionLockRef.current) {
      return
    }

    const startViewTransition = getStartViewTransition()

    if (!startViewTransition || shouldSkipTransition()) {
      toggleTheme()
      return
    }

    transitionLockRef.current = true

    const root = document.documentElement
    prepareTransition(root, originEl ?? triggerRef.current, duration, easing)

    try {
      const transition = startViewTransition(() => {
        const nextDark = !useThemeStore.getState().darkMode
        root.dataset.theme = nextDark ? 'dark' : 'light'
        root.classList.toggle('dark', nextDark)
        flushSync(() => {
          toggleTheme()
        })
      })

      await transition.ready
      await (transition.finished ?? wait(duration))
    } catch (error) {
      console.warn('[theme transition] failed:', error)
    } finally {
      clearPreparedTransition(root)
      transitionLockRef.current = false
    }
  }, [duration, easing, toggleTheme])

  return { runTransition, triggerRef }
}

export type { UseThemeViewTransitionOptions, ViewTransitionLike, StartViewTransition } from './types'