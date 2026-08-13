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

function mockDevicePixelRatio(value: number) {
  Object.defineProperty(window, 'devicePixelRatio', {
    configurable: true,
    writable: true,
    value,
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

function createViewTransition() {
  return {
    ready: Promise.resolve(),
    finished: Promise.resolve(),
    updateCallbackDone: Promise.resolve(),
    skipTransition: vi.fn(),
    types: new Set<string>(),
  }
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
    Object.defineProperty(window, 'requestAnimationFrame', {
      configurable: true,
      writable: true,
      value: (callback: FrameRequestCallback) => window.setTimeout(() => callback(performance.now()), 0),
    })
    mockViewport(2000, 1000)
    mockDevicePixelRatio(1)
  })

  it('warms up the View Transition pseudo tree after mount before the first click', async () => {
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    renderHook(() => useThemeViewTransition({ toggleTheme: vi.fn() }))

    await waitFor(() => {
      expect(startViewTransition).toHaveBeenCalledTimes(1)
    })
    expect(useThemeStore.getState().darkMode).toBe(false)
  })

  it('animates linearly from the clicked trigger after the mount warmup has completed', async () => {
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ duration: 280, toggleTheme }))
    const trigger = document.createElement('button')
    mockButtonRect(trigger, { top: 72, left: 1900, width: 40, height: 40 })

    await waitFor(() => {
      expect(startViewTransition).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.runTransition(trigger)
    })

    expect(startViewTransition).toHaveBeenCalledTimes(2)
    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(animateMock).toHaveBeenCalledWith(
      {
        opacity: [1, 1],
        clipPath: [
          'circle(0px at 1920px 92px)',
          'circle(2123.879469273151px at 1920px 92px)',
        ],
      },
      {
        duration: 280,
        easing: 'linear',
        fill: 'both',
        pseudoElement: '::view-transition-new(root)',
      },
    )
  })

  it('waits for in-flight warmup before starting the first user transition', async () => {
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    let resolveWarmup!: () => void
    const warmupFinished = new Promise<void>((resolve) => {
      resolveWarmup = resolve
    })
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      if (startViewTransition.mock.calls.length === 1) {
        return {
          ...createViewTransition(),
          finished: warmupFinished,
        }
      }
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ duration: 280, toggleTheme }))

    let transitionPromise!: Promise<void>
    act(() => {
      transitionPromise = result.current.runTransition()
    })

    await Promise.resolve()
    expect(startViewTransition).toHaveBeenCalledTimes(1)
    expect(useThemeStore.getState().darkMode).toBe(false)

    await act(async () => {
      resolveWarmup()
      await transitionPromise
    })

    expect(startViewTransition).toHaveBeenCalledTimes(2)
    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(animateMock).toHaveBeenCalled()
  })

  it('suppresses page css transitions while the custom reveal is running', async () => {
    let resolveAnimation!: () => void
    const animationFinished = new Promise<void>((resolve) => {
      resolveAnimation = resolve
    })
    const animateMock = vi.fn().mockReturnValue({ finished: animationFinished })
    document.documentElement.animate = animateMock
    let classNameDuringUpdate = ''
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      if (startViewTransition.mock.calls.length === 2) {
        classNameDuringUpdate = document.documentElement.className
      }
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ duration: 280, toggleTheme }))

    await waitFor(() => {
      expect(startViewTransition).toHaveBeenCalledTimes(1)
    })

    let transitionPromise!: Promise<void>
    await act(async () => {
      transitionPromise = result.current.runTransition()
      await waitFor(() => {
        expect(animateMock).toHaveBeenCalled()
      })
    })

    expect(classNameDuringUpdate).toContain('theme-transition-active')
    expect(document.documentElement).toHaveClass('theme-transition-active')

    await act(async () => {
      resolveAnimation()
      await transitionPromise
    })

    expect(document.documentElement).not.toHaveClass('theme-transition-active')
  })

  it('scales the reveal geometry for high-density Chrome view-transition snapshots', async () => {
    mockDevicePixelRatio(2)
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ duration: 280, toggleTheme }))
    const trigger = document.createElement('button')
    mockButtonRect(trigger, { top: 72, left: 1900, width: 40, height: 40 })

    await waitFor(() => {
      expect(startViewTransition).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.runTransition(trigger)
    })

    expect(animateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        clipPath: [
          'circle(0px at 3840px 184px)',
          'circle(4247.758938546302px at 3840px 184px)',
        ],
      }),
      expect.objectContaining({
        pseudoElement: '::view-transition-new(root)',
      }),
    )
  })

  it('uses the high-density correction only for the first visible transition', async () => {
    mockDevicePixelRatio(2)
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ duration: 280, toggleTheme }))
    const trigger = document.createElement('button')
    mockButtonRect(trigger, { top: 72, left: 1900, width: 40, height: 40 })

    await waitFor(() => {
      expect(startViewTransition).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.runTransition(trigger)
      await result.current.runTransition(trigger)
    })

    expect(animateMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        clipPath: [
          'circle(0px at 3840px 184px)',
          'circle(4247.758938546302px at 3840px 184px)',
        ],
      }),
      expect.objectContaining({
        pseudoElement: '::view-transition-new(root)',
      }),
    )
    expect(animateMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        clipPath: [
          'circle(0px at 1920px 92px)',
          'circle(2123.879469273151px at 1920px 92px)',
        ],
      }),
      expect.objectContaining({
        pseudoElement: '::view-transition-new(root)',
      }),
    )
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
    const startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return createViewTransition()
    })
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = startViewTransition

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))

    await act(async () => {
      await result.current.runTransition()
    })

    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(startViewTransition).not.toHaveBeenCalled()
    expect(animateMock).not.toHaveBeenCalled()
  })

  it('switches immediately when View Transition API is unavailable', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))

    await act(async () => {
      await result.current.runTransition()
    })

    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(animateMock).not.toHaveBeenCalled()
  })
})
