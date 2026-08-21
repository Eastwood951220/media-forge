import { DownOutlined, UpOutlined } from '@ant-design/icons'
import { Button, Card } from 'antd'
import { clsx } from 'clsx'
import { useState, type PropsWithChildren, type ReactNode } from 'react'
import styles from './SectionCard.module.less'

export interface SectionCardProps {
  title?: ReactNode
  extra?: ReactNode
  collapsible?: boolean
  defaultExpanded?: boolean
  className?: string
}

export function SectionCard({
  title,
  collapsible,
  defaultExpanded = true,
  children,
  extra,
  className,
}: PropsWithChildren<SectionCardProps>) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const collapseExtra = collapsible ? (
    <Button
      type="text"
      size="small"
      icon={expanded ? <UpOutlined /> : <DownOutlined />}
      aria-label={expanded ? `收起${title ?? ''}` : `展开${title ?? ''}`}
      onClick={() => setExpanded((value) => !value)}
    />
  ) : null
  return (
    <Card
      title={title}
      extra={extra ?? collapseExtra}
      className={clsx(styles.sectionCard, className)}
    >
      {expanded || !collapsible ? children : null}
    </Card>
  )
}
