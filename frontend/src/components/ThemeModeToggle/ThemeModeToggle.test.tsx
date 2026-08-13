import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeModeToggle } from './index'
import { useThemeStore } from '@/stores/useThemeStore'

describe('ThemeModeToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete (document as Document & { startViewTransition?: unknown }).startViewTransition
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
    expect(button).not.toHaveClass('theme-toggle--toggled')

    await userEvent.click(button)

    await waitFor(() => {
      expect(useThemeStore.getState().darkMode).toBe(true)
    })
    expect(button).toHaveClass('theme-toggle--toggled')
    expect(button).not.toBeDisabled()
  })

  it('keeps login label copy while using the animated button', () => {
    useThemeStore.setState({ mode: 'dark', darkMode: true, primaryColor: '#006AFF' })

    render(<ThemeModeToggle variant="login" />)

    expect(screen.getByText('深色模式')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '切换明暗模式' })).toHaveClass('theme-toggle--toggled')
  })
})