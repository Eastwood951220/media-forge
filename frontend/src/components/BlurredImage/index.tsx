import { type CSSProperties, type ImgHTMLAttributes, type ReactNode, type SyntheticEvent, useCallback, useEffect, useRef } from 'react'
import { Image } from 'antd'
import { clsx } from 'clsx'
import { useImageBlurStore } from '@/stores/useImageBlurStore'
import styles from './BlurredImage.module.less'

type BlurredImageProps = {
  src?: string | null
  alt: string
  className?: string
  imageClassName?: string
  fallback?: ReactNode
  preview?: boolean
  stopPropagation?: boolean
  onPreviewVisibleChange?: (visible: boolean) => void
  loading?: 'eager' | 'lazy'
  referrerPolicy?: ImgHTMLAttributes<HTMLImageElement>['referrerPolicy']
}

function mediaBackdropStyle(url: string): CSSProperties {
  return { '--media-bg': `url("${url}")` } as CSSProperties
}

export function isImagePreviewEvent(event: Pick<SyntheticEvent, 'target'>) {
  const target = event.target
  return target instanceof Element && Boolean(target.closest('.ant-image-preview-root'))
}

export function useImagePreviewNavigationGuard() {
  const previewOpenRef = useRef(false)
  const suppressNextNavigationRef = useRef(false)
  const clearSuppressionTimerRef = useRef<number | undefined>(undefined)

  useEffect(() => () => {
    if (clearSuppressionTimerRef.current !== undefined) {
      window.clearTimeout(clearSuppressionTimerRef.current)
    }
  }, [])

  const onPreviewVisibleChange = useCallback((visible: boolean) => {
    if (!visible && previewOpenRef.current) {
      suppressNextNavigationRef.current = true
      if (clearSuppressionTimerRef.current !== undefined) {
        window.clearTimeout(clearSuppressionTimerRef.current)
      }
      clearSuppressionTimerRef.current = window.setTimeout(() => {
        suppressNextNavigationRef.current = false
      }, 0)
    }
    previewOpenRef.current = visible
  }, [])

  const shouldIgnoreNavigation = useCallback((event: Pick<SyntheticEvent, 'target'>) => (
    previewOpenRef.current || suppressNextNavigationRef.current || isImagePreviewEvent(event)
  ), [])

  return {
    onPreviewVisibleChange,
    shouldIgnoreNavigation,
  }
}

export function BlurredImage({
  src,
  alt,
  className,
  imageClassName,
  fallback = null,
  preview = true,
  stopPropagation = true,
  onPreviewVisibleChange,
  loading = 'lazy',
  referrerPolicy,
}: BlurredImageProps) {
  const blurEnabled = useImageBlurStore((state) => state.enabled)

  if (!src) {
    return <div className={clsx(styles.root, className)}>{fallback}</div>
  }

  const stopEventPropagation = (event: SyntheticEvent) => {
    if (stopPropagation) event.stopPropagation()
  }

  return (
    <div
      className={clsx(styles.root, className)}
      style={mediaBackdropStyle(src)}
    >
      <Image
        src={src}
        alt={alt}
        aria-label={preview ? `预览 ${alt}` : alt}
        className={clsx(blurEnabled && styles.blurred, imageClassName)}
        loading={loading}
        preview={preview ? { onOpenChange: onPreviewVisibleChange } : false}
        referrerPolicy={referrerPolicy}
        onClick={stopEventPropagation}
        onKeyDown={stopEventPropagation}
      />
    </div>
  )
}
