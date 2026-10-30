import { useEffect, useRef, useState } from 'react'
import type { Movie } from '@/api/movie/types'
import { fetchScrapedMovieCover } from '@/api/movie'
import { BlurredImage } from '@/components/BlurredImage'
import styles from '../MovieListPage.module.less'

interface MovieCoverImageProps {
  movie: Pick<Movie, 'id' | 'code' | 'cover' | 'scraping_status' | 'scraping_folder' | 'scraping_checked_at'>
  className: string
}

export function MovieCoverImage({ movie, className }: MovieCoverImageProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)
  const [loaded, setLoaded] = useState<{ key: string; url: string } | null>(null)
  const [failedKey, setFailedKey] = useState<string | null>(null)
  const scraped = movie.scraping_status === 'scraped' && Boolean(movie.scraping_folder)
  const coverKey = `${movie.id}:${movie.scraping_folder ?? ''}:${movie.scraping_checked_at ?? ''}`

  useEffect(() => {
    if (!scraped || visible) return
    const element = containerRef.current
    if (!element || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true)
        observer.disconnect()
      }
    }, { rootMargin: '200px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [scraped, visible])

  useEffect(() => {
    if (!scraped || !visible) return
    const controller = new AbortController()
    let url: string | null = null
    fetchScrapedMovieCover(movie.id, controller.signal, movie.scraping_checked_at)
      .then((blob) => {
        if (controller.signal.aborted) return
        url = URL.createObjectURL(blob)
        setLoaded({ key: coverKey, url })
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailedKey(coverKey)
      })
    return () => {
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [coverKey, movie.id, movie.scraping_checked_at, scraped, visible])

  const localSrc = loaded?.key === coverKey ? loaded.url : null
  const src = scraped ? localSrc || (failedKey === coverKey ? movie.cover : '') : movie.cover

  if (!src && (!scraped || failedKey === coverKey)) return <span>-</span>
  return (
    <div ref={containerRef} className={className}>
      <BlurredImage
        src={src}
        alt={movie.code || '封面'}
        className={styles.coverImage}
        fallback={<span className={styles.coverPlaceholder} aria-label="封面加载中" />}
        referrerPolicy="no-referrer"
      />
    </div>
  )
}
