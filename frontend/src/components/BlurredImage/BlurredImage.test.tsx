import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useImageBlurStore } from '@/stores/useImageBlurStore'
import { BlurredImage } from './index'

describe('BlurredImage', () => {
  beforeEach(() => {
    useImageBlurStore.setState({ enabled: true })
  })

  it('renders a complete image with the global blur state applied', () => {
    render(<BlurredImage src="https://example.test/cover.jpg" alt="封面" />)

    const image = screen.getByAltText('封面')
    expect(image).toHaveAttribute('src', 'https://example.test/cover.jpg')
    expect(image.className).toMatch(/blurred/)
    expect(screen.getByRole('button', { name: '预览 封面' })).toBeInTheDocument()
  })

  it('stops click propagation while opening preview from nested cards', () => {
    const onParentClick = vi.fn()

    render(
      <div onClick={onParentClick}>
        <BlurredImage src="https://example.test/cover.jpg" alt="封面" />
      </div>,
    )

    fireEvent.click(screen.getByRole('button', { name: '预览 封面' }))

    expect(onParentClick).not.toHaveBeenCalled()
  })
})
