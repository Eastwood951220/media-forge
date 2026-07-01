import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * Tailwind default breakpoints (px).
 * sm:640 md:768 lg:1024 xl:1280 2xl:1536
 *
 * We define "mobile" as < 768 (below md).
 */

const MOBILE_MAX = 767
const TABLET_MAX = 991

type Breakpoint = 'mobile' | 'tablet' | 'desktop'

interface BreakpointInfo {
  breakpoint: Breakpoint
  isMobile: boolean
  isTablet: boolean
  isDesktop: boolean
  screenWidth: number
}

function getBreakpoint(width: number): Breakpoint {
  if (width <= MOBILE_MAX) return 'mobile'
  if (width <= TABLET_MAX) return 'tablet'
  return 'desktop'
}

/**
 * Reactive breakpoint hook — SSR-safe.
 *
 * Re-renders only when the breakpoint bucket changes,
 * not on every pixel resize.
 */
export function useBreakpoint(): BreakpointInfo {
  const [info, setInfo] = useState<BreakpointInfo>(() => {
    if (typeof window === 'undefined') {
      return { breakpoint: 'desktop', isMobile: false, isTablet: false, isDesktop: true, screenWidth: 1280 }
    }
    const w = window.innerWidth
    const bp = getBreakpoint(w)
    return {
      breakpoint: bp,
      isMobile: bp === 'mobile',
      isTablet: bp === 'tablet',
      isDesktop: bp === 'desktop',
      screenWidth: w,
    }
  })

  const prevBpRef = useRef<Breakpoint>(info.breakpoint)

  const handleResize = useCallback(() => {
    const w = window.innerWidth
    const bp = getBreakpoint(w)
    if (bp !== prevBpRef.current) {
      prevBpRef.current = bp
      setInfo({
        breakpoint: bp,
        isMobile: bp === 'mobile',
        isTablet: bp === 'tablet',
        isDesktop: bp === 'desktop',
        screenWidth: w,
      })
    }
  }, [])

  useEffect(() => {
    window.addEventListener('resize', handleResize)
    handleResize()
    return () => window.removeEventListener('resize', handleResize)
  }, [handleResize])

  return info
}

/**
 * Convenience hook — returns true when viewport < 768px.
 */
export function useMobile(): boolean {
  return useBreakpoint().isMobile
}
