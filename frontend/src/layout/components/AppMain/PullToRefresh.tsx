import { useState, useRef, useCallback, type TouchEvent } from 'react'
import { LoadingOutlined, DownOutlined } from '@ant-design/icons'
import { useMobile } from '@/hooks/useBreakpoint'
import styles from './index.module.less'

const PULL_THRESHOLD = 80

type PullState = 'idle' | 'pulling' | 'loading' | 'resetting'

interface PullToRefreshProps {
  onRefresh: () => Promise<void>
  children: React.ReactNode
}

export default function PullToRefresh({ onRefresh, children }: PullToRefreshProps) {
  const isMobile = useMobile()
  const [pullState, setPullState] = useState<PullState>('idle')
  const [pullDistance, setPullDistance] = useState(0)
  const startYRef = useRef(0)
  const isPullingRef = useRef(false)

  const handleTouchStart = useCallback((e: TouchEvent) => {
    const scrollTop = (e.currentTarget as HTMLElement).scrollTop
    if (scrollTop > 0) return
    startYRef.current = e.touches[0].clientY
    isPullingRef.current = true
  }, [])

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!isPullingRef.current) return
      const currentY = e.touches[0].clientY
      const distance = Math.max(0, currentY - startYRef.current)
      const dampenedDistance = Math.min(distance * 0.5, 120)
      setPullDistance(dampenedDistance)
      setPullState(dampenedDistance > 0 ? 'pulling' : 'idle')
    },
    [],
  )

  const handleTouchEnd = useCallback(async () => {
    if (!isPullingRef.current) return
    isPullingRef.current = false

    if (pullDistance >= PULL_THRESHOLD) {
      setPullState('loading')
      setPullDistance(40)
      try {
        await onRefresh()
      } catch {
        // Refresh callback handles its own errors
      }
    }
    setPullState('resetting')
    setPullDistance(0)
    setTimeout(() => setPullState('idle'), 300)
  }, [pullDistance, onRefresh])

  if (!isMobile) {
    return <>{children}</>
  }

  const indicatorClass = [
    styles['pull-indicator'],
    pullState === 'pulling' && styles['pull-indicator--pulling'],
    pullState === 'loading' && styles['pull-indicator--loading'],
    pullState === 'resetting' && styles['pull-indicator--resetting'],
  ]
    .filter(Boolean)
    .join(' ')

  const contentClass = [
    styles['pull-content'],
    pullState === 'pulling' && styles['pull-content--pulling'],
    pullState === 'loading' && styles['pull-content--loading'],
    pullState === 'resetting' && styles['pull-content--resetting'],
  ]
    .filter(Boolean)
    .join(' ')

  const arrowClass = [
    styles['pull-arrow'],
    pullDistance >= PULL_THRESHOLD && styles['pull-arrow--flipped'],
  ]
    .filter(Boolean)
    .join(' ')

  const pullHeight = pullState === 'pulling' ? `${pullDistance}px` : undefined

  return (
    <div
      className={styles['pull-to-refresh']}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <div
        className={indicatorClass}
        style={pullHeight ? { '--pull-height': pullHeight } as React.CSSProperties : undefined}
      >
        {pullState === 'loading' ? (
          <LoadingOutlined spin />
        ) : (
          <span className={arrowClass}>
            <DownOutlined />
          </span>
        )}
      </div>
      <div
        className={contentClass}
        style={pullHeight ? { '--pull-height': pullHeight } as React.CSSProperties : undefined}
      >
        {children}
      </div>
    </div>
  )
}
