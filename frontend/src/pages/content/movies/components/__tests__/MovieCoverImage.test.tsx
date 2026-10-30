import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchScrapedMovieCover } from '@/api/movie'
import { MovieCoverImage } from '../MovieCoverImage'

vi.mock('@/api/movie', () => ({ fetchScrapedMovieCover: vi.fn() }))

const movie = {
  id: 'movie-1',
  code: 'AAA-001',
  cover: 'https://example.test/original.jpg',
  scraping_status: 'scraped' as const,
  scraping_folder: '/media/AAA-001',
  scraping_checked_at: '2026-10-30T00:00:00Z',
}

describe('MovieCoverImage', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:scraped-cover') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  })

  afterEach(() => vi.clearAllMocks())

  it('uses the scraped cover when available', async () => {
    vi.mocked(fetchScrapedMovieCover).mockResolvedValue(new Blob(['image'], { type: 'image/jpeg' }))

    render(<MovieCoverImage movie={movie} className="cover" />)

    expect(await screen.findByAltText('AAA-001')).toHaveAttribute('src', 'blob:scraped-cover')
    expect(fetchScrapedMovieCover).toHaveBeenCalledWith('movie-1', expect.any(AbortSignal), movie.scraping_checked_at)
  })

  it('falls back to the original cover when the local image is missing', async () => {
    vi.mocked(fetchScrapedMovieCover).mockRejectedValue(new Error('missing'))

    render(<MovieCoverImage movie={movie} className="cover" />)

    expect(await screen.findByAltText('AAA-001')).toHaveAttribute('src', movie.cover)
  })

  it('uses the original cover without a local request for an unscraped movie', () => {
    render(<MovieCoverImage movie={{ ...movie, scraping_status: 'not_scraped' }} className="cover" />)

    expect(screen.getByAltText('AAA-001')).toHaveAttribute('src', movie.cover)
    expect(fetchScrapedMovieCover).not.toHaveBeenCalled()
  })
})
