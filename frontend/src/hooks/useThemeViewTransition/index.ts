import { useCallback, useEffect, useRef } from 'react'
import { flushSync } from 'react-dom'
import type {
  StartViewTransition,
  UseThemeViewTransitionOptions,
} from './types'

const DEFAULT_DURATION = 1200
const DEFAULT_EASING = 'linear'
const TOP_RIGHT_ORIGIN_INSET = 44
const THEME_TRANSITION_ACTIVE_CLASS = 'theme-transition-active'

function shouldSkipTransition(): boolean {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return true
  }

  return (
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  )
}

function getStartViewTransition(): StartViewTransition | null {
  if (typeof document === 'undefined') {
    return null
  }

  const doc = document as Document & {
    startViewTransition?: StartViewTransition
  }

  const fn = doc.startViewTransition

  return typeof fn === 'function' ? fn.bind(doc) : null
}

function getTransitionOrigin(originEl?: HTMLElement | null) {
  if (originEl) {
    const rect = originEl.getBoundingClientRect()

    return {
      x: rect.left + rect.width / 2,
      y: rect.top + rect.height / 2,
    }
  }

  return {
    x: Math.max(window.innerWidth - TOP_RIGHT_ORIGIN_INSET, 0),
    y: TOP_RIGHT_ORIGIN_INSET,
  }
}

function getViewTransitionCoordinateScale() {
  return Math.max(window.devicePixelRatio || 1, 1)
}

function getCoveringRadius(
  x: number,
  y: number,
  width = window.innerWidth,
  height = window.innerHeight,
) {
  return Math.hypot(
    Math.max(x, width - x),
    Math.max(y, height - y),
  )
}

function waitNextFrame(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      resolve()
    })
  })
}

export function useThemeViewTransition({
  duration = DEFAULT_DURATION,
  easing = DEFAULT_EASING,
  toggleTheme,
}: UseThemeViewTransitionOptions) {
  const transitionLockRef = useRef(false)
  const triggerRef = useRef<HTMLElement | null>(null)
  const warmupCompleteRef = useRef(false)
  const warmupPromiseRef = useRef<Promise<void> | null>(null)

  const ensureWarmup = useCallback((startViewTransition: StartViewTransition) => {
    if (warmupCompleteRef.current) {
      return Promise.resolve()
    }

    if (!warmupPromiseRef.current) {
      warmupPromiseRef.current = (async () => {
        const warmupTransition = startViewTransition(() => {
          // intentionally empty
        })

        await warmupTransition.finished
        await waitNextFrame()
        warmupCompleteRef.current = true
      })().catch((error) => {
        warmupPromiseRef.current = null
        console.warn('[theme transition] warmup failed:', error)
      })
    }

    return warmupPromiseRef.current
  }, [])

  useEffect(() => {
    const startViewTransition = getStartViewTransition()

    if (!startViewTransition || shouldSkipTransition()) {
      return
    }

    void ensureWarmup(startViewTransition)
  }, [ensureWarmup])

  const runTransition = useCallback(
    async (originEl?: HTMLElement | null) => {
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

      /**
       * 必须在任何 await 之前读取点击元素坐标。
       *
       * 避免异步之后 React 更新 / DOM layout 改变导致
       * event/currentTarget 对应位置失效。
       */
      const { x, y } = getTransitionOrigin(
        originEl ?? triggerRef.current,
      )

      const coordinateScale = getViewTransitionCoordinateScale()
      const revealX = x * coordinateScale
      const revealY = y * coordinateScale
      const radius = getCoveringRadius(
        revealX,
        revealY,
        window.innerWidth * coordinateScale,
        window.innerHeight * coordinateScale,
      )

      try {
        await ensureWarmup(startViewTransition)

        root.classList.add(THEME_TRANSITION_ACTIVE_CLASS)

        const transition = startViewTransition(() => {
          flushSync(() => {
            toggleTheme()
          })
        })

        /**
         * ready 完成后：
         * ::view-transition-new(root)
         * 已经真实存在，可以开始 WAAPI 动画。
         */
        await transition.ready

        const animation = root.animate(
          {
            opacity: [1, 1],
            clipPath: [
              `circle(0px at ${revealX}px ${revealY}px)`,
              `circle(${radius}px at ${revealX}px ${revealY}px)`,
            ],
          },
          {
            duration,
            easing,
            fill: 'both',
            pseudoElement: '::view-transition-new(root)',
          },
        )

        await Promise.all([
          animation.finished,
          transition.finished,
        ])
      } catch (error) {
        console.warn('[theme transition] failed:', error)
      } finally {
        root.classList.remove(THEME_TRANSITION_ACTIVE_CLASS)
        transitionLockRef.current = false
      }
    },
    [duration, easing, toggleTheme],
  )

  return {
    runTransition,
    triggerRef,
  }
}

export type {
  UseThemeViewTransitionOptions,
  ViewTransitionLike,
  StartViewTransition,
} from './types'
