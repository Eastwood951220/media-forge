import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useThemeViewTransition } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

type MockViewTransition = ReturnType<typeof vi.fn>

function mockViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  })
  Object.defineProperty(window, 'innerHeight', {
    configurable: true,
    writable: true,
    value: height,
  })
}

function mockButtonRect(element: HTMLElement, rect: Pick<DOMRect, 'top' | 'left' | 'width' | 'height'>) {
  element.getBoundingClientRect = () => ({
    x: rect.left,
    y: rect.top,
    top: rect.top,
    left: rect.left,
    right: rect.left + rect.width,
    bottom: rect.top + rect.height,
    width: rect.width,
    height: rect.height,
    toJSON: () => ({}),
  })
}

describe('useThemeViewTransition', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.startViewTransition = undefined as unknown as Document['startViewTransition']
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
    document.documentElement.removeAttribute('style')
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)' ? false : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    mockViewport(2000, 1000)
  })

  it('prepares button-centered CSS variables before the first View Transition frame', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    let cssStatePreparedBeforeCallback = false
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      cssStatePreparedBeforeCallback =
        document.documentElement.classList.contains('theme-transition-active') &&
        document.documentElement.style.getPropertyValue('--theme-transition-x') === '1920px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-y') === '92px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-radius') === '2123.879469273151px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-duration') === '280ms' &&
        document.documentElement.style.getPropertyValue('--theme-transition-easing') === 'linear'
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    const trigger = document.createElement('button')
    mockButtonRect(trigger, { top: 72, left: 1900, width: 40, height: 40 })

    await act(async () => {
      await result.current.runTransition(trigger)
    })

    expect((document as unknown as { startViewTransition: MockViewTransition }).startViewTransition).toHaveBeenCalledTimes(1)
    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(cssStatePreparedBeforeCallback).toBe(true)
    expect(animateMock).not.toHaveBeenCalled()
    expect(document.documentElement).not.toHaveClass('theme-transition-active')
    expect(document.documentElement.style.getPropertyValue('--theme-transition-x')).toBe('')
  })

  it('falls back to the upper-right visible point when no trigger is supplied', async () => {
    let cssStatePreparedBeforeCallback = false
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      cssStatePreparedBeforeCallback =
        document.documentElement.style.getPropertyValue('--theme-transition-x') === '1956px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-y') === '44px' &&
        document.documentElement.style.getPropertyValue('--theme-transition-radius') === '2177.1247093356874px'
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))

    await act(async () => {
      await result.current.runTransition()
    })

    expect(cssStatePreparedBeforeCallback).toBe(true)
    expect(useThemeStore.getState().darkMode).toBe(true)
  })

  it('switches immediately without root animation when reduced motion is requested', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    ;(window.matchMedia as MockViewTransition).mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return { ready: Promise.resolve(), finished: Promise.resolve(), updateCallbackDone: Promise.resolve(), skipTransition: () => {}, types: new Set<string>() }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    result.current.triggerRef.current = document.createElement('button') as never

    await act(async () => {
      await result.current.runTransition()
    })

    expect(useThemeStore.getState().darkMode).toBe(true)
    expect((document as unknown as { startViewTransition: MockViewTransition }).startViewTransition).not.toHaveBeenCalled()
    expect(animateMock).not.toHaveBeenCalled()
  })

  it('switches immediately when View Transition API is unavailable', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    result.current.triggerRef.current = document.createElement('button') as never

    await act(async () => {
      await result.current.runTransition()
    })

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(animateMock).not.toHaveBeenCalled()
  })
})