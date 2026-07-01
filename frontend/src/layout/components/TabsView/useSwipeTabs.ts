import { useRef, useCallback } from 'react'

const SWIPE_THRESHOLD = 50

type TouchState = {
  startX: number
  startY: number
  startTime: number
}

type SwipeCallbacks = {
  onSwipeLeft?: () => void
  onSwipeRight?: () => void
}

type SwipeHandlers = {
  onTouchStart: React.TouchEventHandler<HTMLDivElement>
  onTouchMove: React.TouchEventHandler<HTMLDivElement>
  onTouchEnd: React.TouchEventHandler<HTMLDivElement>
}

/**
 * Custom hook for detecting horizontal swipe gestures on touch devices.
 *
 * - Ignores vertical swipes (distanceY > distanceX)
 * - Requires horizontal distance >= 50px to trigger
 * - Uses refs for touch state to avoid re-renders
 */
export function useSwipeTabs({ onSwipeLeft, onSwipeRight }: SwipeCallbacks): SwipeHandlers {
  const touchState = useRef<TouchState | null>(null)

  const onTouchStart = useCallback<React.TouchEventHandler<HTMLDivElement>>((event) => {
    const touch = event.touches[0]
    if (!touch) return
    touchState.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      startTime: Date.now(),
    }
  }, [])

  const onTouchMove = useCallback<React.TouchEventHandler<HTMLDivElement>>(() => {
    // No-op: we calculate direction on touchEnd
  }, [])

  const onTouchEnd = useCallback<React.TouchEventHandler<HTMLDivElement>>((event) => {
    const state = touchState.current
    touchState.current = null

    if (!state) return

    const touch = event.changedTouches[0]
    if (!touch) return

    const deltaX = touch.clientX - state.startX
    const deltaY = touch.clientY - state.startY

    // Ignore vertical swipes
    if (Math.abs(deltaY) > Math.abs(deltaX)) return

    // Check threshold
    if (Math.abs(deltaX) < SWIPE_THRESHOLD) return

    if (deltaX < 0) {
      onSwipeLeft?.()
    } else {
      onSwipeRight?.()
    }
  }, [onSwipeLeft, onSwipeRight])

  return { onTouchStart, onTouchMove, onTouchEnd }
}
