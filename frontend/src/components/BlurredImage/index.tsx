import { type CSSProperties, type ImgHTMLAttributes, type ReactNode, type SyntheticEvent } from 'react'
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
        preview={preview}
        referrerPolicy={referrerPolicy}
        onClick={stopEventPropagation}
        onKeyDown={stopEventPropagation}
      />
    </div>
  )
}
