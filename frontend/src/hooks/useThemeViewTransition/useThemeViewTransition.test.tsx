import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useThemeViewTransition } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

type MockViewTransition = ReturnType<typeof vi.fn>

describe('useThemeViewTransition', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.startViewTransition = undefined as unknown as Document['startViewTransition']
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
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
  })

  it('animates the root view transition with tuned duration and easing', async () => {
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    ;(document as unknown as { startViewTransition: MockViewTransition }).startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return { ready: Promise.resolve(), finished: Promise.resolve(), updateCallbackDone: Promise.resolve(), skipTransition: () => {}, types: new Set<string>() }
    })

    const toggleTheme = () => useThemeStore.getState().toggleMode()
    const { result } = renderHook(() => useThemeViewTransition({ toggleTheme }))
    const trigger = document.createElement('div')
    trigger.getBoundingClientRect = () => ({
      x: 12,
      y: 20,
      top: 20,
      left: 12,
      right: 52,
      bottom: 60,
      width: 40,
      height: 40,
      toJSON: () => ({}),
    })
    result.current.triggerRef.current = trigger

    await act(async () => {
      await result.current.runTransition()
    })

    expect((document as unknown as { startViewTransition: MockViewTransition }).startViewTransition).toHaveBeenCalledTimes(1)
    expect(useThemeStore.getState().darkMode).toBe(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement).toHaveClass('dark')
    expect(animateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        clipPath: [
          'circle(0px at 32px 40px)',
          expect.stringMatching(/^circle\(.+px at 32px 40px\)$/),
        ],
      }),
      expect.objectContaining({
        duration: 280,
        easing: 'cubic-bezier(0.2, 0, 0, 1)',
        pseudoElement: '::view-transition-new(root)',
      }),
    )
    expect(document.documentElement).not.toHaveClass('theme-transition-active')
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
    result.current.triggerRef.current = document.createElement('div')

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
    result.current.triggerRef.current = document.createElement('div')

    await act(async () => {
      await result.current.runTransition()
    })

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(animateMock).not.toHaveBeenCalled()
  })
})