import { useState, type CSSProperties, type ImgHTMLAttributes, type ReactNode, type SyntheticEvent } from 'react'
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
  loading?: 'eager' | 'lazy'
  referrerPolicy?: ImgHTMLAttributes<HTMLImageElement>['referrerPolicy']
}

function mediaBackdropStyle(url: string): CSSProperties {
  return { '--media-bg': `url("${url}")` } as CSSProperties
}

export function BlurredImage({
  src,
  alt,
  className,
  imageClassName,
  fallback = null,
  preview = true,
  stopPropagation = true,
  loading = 'lazy',
  referrerPolicy,
}: BlurredImageProps) {
  const blurEnabled = useImageBlurStore((state) => state.enabled)
  const [previewOpen, setPreviewOpen] = useState(false)

  if (!src) {
    return <div className={clsx(styles.root, className)}>{fallback}</div>
  }

  const openPreview = () => {
    if (preview) setPreviewOpen(true)
  }

  const stopEventPropagation = (event: SyntheticEvent) => {
    if (stopPropagation) event.stopPropagation()
  }

  return (
    <div
      aria-label={`预览 ${alt}`}
      className={clsx(styles.root, className)}
      role={preview ? 'button' : undefined}
      tabIndex={preview ? 0 : undefined}
      style={mediaBackdropStyle(src)}
      onClick={(event) => {
        stopEventPropagation(event)
        openPreview()
      }}
      onKeyDown={(event) => {
        if (!preview) return
        if (event.key !== 'Enter' && event.key !== ' ') return
        event.preventDefault()
        stopEventPropagation(event)
        openPreview()
      }}
    >
      <Image
        src={src}
        alt={alt}
        className={clsx(blurEnabled && styles.blurred, imageClassName)}
        loading={loading}
        preview={preview ? { open: previewOpen, onOpenChange: setPreviewOpen } : false}
        referrerPolicy={referrerPolicy}
      />
    </div>
  )
}
