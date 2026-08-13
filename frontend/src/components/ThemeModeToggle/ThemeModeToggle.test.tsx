// @ts-nocheck - test file, uses require('react') inside hoisted mock factory
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeModeToggle } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

vi.mock('@theme-toggles/react/styles/classic.css', () => ({}))

vi.mock('@theme-toggles/react', () => {
  const React = require('react')
  const Classic = React.forwardRef<HTMLButtonElement, Record<string, unknown>>(
    (props, ref) => {
      const className = props.className
      const ariaLabel = props['aria-label']
      const onClick = props.onClick
      return React.createElement('button', {
        className,
        'aria-label': ariaLabel,
        onClick,
        ref,
        type: 'button',
        title: props.title,
      })
    },
  )
  Classic.displayName = 'Classic'
  return { Classic }
})

describe('ThemeModeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    document.startViewTransition = undefined as unknown as Document['startViewTransition']
    useThemeStore.setState({
      mode: 'light',
      darkMode: false,
      primaryColor: '#006AFF',
    })
    document.documentElement.dataset.theme = 'light'
    document.documentElement.className = ''
    document.documentElement.removeAttribute('style')
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
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      writable: true,
      value: 2000,
    })
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      writable: true,
      value: 1000,
    })
  })

  it('renders an accessible animated theme button instead of an Ant Design switch', () => {
    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    expect(button).toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: '切换明暗模式' })).not.toBeInTheDocument()
    expect(button).toHaveClass('theme-toggle')
    expect(button).not.toHaveClass('ant-switch')
  })

  it('uses store state as the toggled visual state and toggles theme on click', async () => {
    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    await userEvent.click(button)

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(button).not.toBeDisabled()
  })

  it('keeps login label copy while using the animated button', () => {
    useThemeStore.setState({ mode: 'dark', darkMode: true, primaryColor: '#006AFF' })

    render(<ThemeModeToggle variant="login" />)

    expect(screen.getByText('深色模式')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '切换明暗模式' })).toHaveClass('theme-toggle')
  })

  it('prepares CSS origin from the clicked theme button before the first transition frame', async () => {
    const animateMock = vi.fn()
    document.documentElement.animate = animateMock
    let cssStatePreparedBeforeCallback = false
    document.startViewTransition = vi.fn((callback: () => void) => {
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
    }) as unknown as Document['startViewTransition']

    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    button.getBoundingClientRect = () => ({
      x: 1900,
      y: 72,
      top: 72,
      left: 1900,
      right: 1940,
      bottom: 112,
      width: 40,
      height: 40,
      toJSON: () => ({}),
    })

    await userEvent.click(button)

    await waitFor(() => {
      expect(cssStatePreparedBeforeCallback).toBe(true)
    })
    expect(animateMock).not.toHaveBeenCalled()
  })
})