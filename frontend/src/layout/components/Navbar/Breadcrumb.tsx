import { Breadcrumb as AntBreadcrumb } from 'antd'
import { useMatches } from '@tanstack/react-router'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import styles from './index.module.less'

/** Human-readable labels for known routes. */
const ROUTE_LABELS: Record<string, string> = {
  '/': '首页',
  '/login': '登录',
  '/init': '初始化',
}

function getLabel(pathname: string): string {
  return ROUTE_LABELS[pathname] ?? pathname
}

/**
 * Shows the current page breadcrumb on desktop.
 * Hidden on mobile via CSS (hamburger alone is sufficient).
 */
export default function BreadcrumbNav() {
  const { isMobile } = useBreakpoint()
  const matches = useMatches()

  if (isMobile) {
    return null
  }

  const current = matches[matches.length - 1]
  const label = getLabel(current?.pathname ?? '/')

  return (
    <AntBreadcrumb className={styles.breadcrumb}>
      <AntBreadcrumb.Item>{label}</AntBreadcrumb.Item>
    </AntBreadcrumb>
  )
}
