// @ts-nocheck — test file, uses require('react') inside hoisted mock factory
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeModeToggle } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

// Mock @theme-toggles/react CSS since it uses Tailwind v4 syntax jsdom can't parse
vi.mock('@theme-toggles/react/styles/classic.css', () => ({}))

// Mock @theme-toggles/react since it ships raw TSX without React imports
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
  })

  it('renders an accessible animated theme button instead of an Ant Design switch', () => {
    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    expect(button).toBeInTheDocument()
    expect(screen.queryByRole('switch', { name: '切换明暗模式' })).not.toBeInTheDocument()
    expect(button).toHaveClass('theme-toggle')
    expect(button).not.toHaveClass('ant-switch')
    expect(button).not.toHaveClass('ant-switch-loading')
    expect(button).not.toHaveClass('ant-switch-disabled')
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

  it('uses the wrapper div as the view-transition origin matching button position', async () => {
    const animateMock = vi.fn().mockReturnValue({ finished: Promise.resolve() })
    document.documentElement.animate = animateMock
    document.startViewTransition = vi.fn((callback: () => void) => {
      callback()
      return {
        ready: Promise.resolve(),
        finished: Promise.resolve(),
        updateCallbackDone: Promise.resolve(),
        skipTransition: () => {},
        types: new Set<string>(),
      }
    }) as unknown as Document['startViewTransition']
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

    render(<ThemeModeToggle />)

    const button = screen.getByRole('button', { name: '切换明暗模式' })
    const wrapper = button.parentElement!
    wrapper.getBoundingClientRect = () => ({
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
      expect(animateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          clipPath: [
            'circle(0px at 1920px 92px)',
            expect.stringMatching(/^circle\(.+px at 1920px 92px\)$/),
          ],
        }),
        expect.objectContaining({
          duration: 280,
          easing: 'linear',
          pseudoElement: '::view-transition-new(root)',
        }),
      )
    })
  })
})