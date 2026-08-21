import { clsx } from 'clsx'
import type { PropsWithChildren } from 'react'
import styles from './PageShell.module.less'

export function PageShell({
  children,
  className,
}: PropsWithChildren<{ className?: string }>) {
  return <div className={clsx(styles.pageShell, className)}>{children}</div>
}
