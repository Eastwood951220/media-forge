import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { DownOutlined } from '@ant-design/icons'
import { Button, Popconfirm, Popover } from 'antd'
import type { ButtonProps, PopconfirmProps } from 'antd'
import styles from './ResponsiveActions.module.less'

const ACTION_BUTTON_WIDTH = 72
const MORE_BUTTON_WIDTH = 64
const ACTION_GAP = 4

export type ResponsiveAction = {
  key: string
  label: ReactNode
  icon?: ReactNode
  type?: ButtonProps['type']
  danger?: boolean
  disabled?: boolean
  loading?: boolean
  confirm?: Pick<
    PopconfirmProps,
    'title' | 'description' | 'okText' | 'cancelText' | 'okType'
  >
  onClick?: () => void | Promise<void>
}

export interface ResponsiveActionsProps {
  actions: ResponsiveAction[]
  minInlineCount?: number
}

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return

      const nextWidth = Math.round(entry.contentRect.width)
      setWidth((previousWidth) => previousWidth === nextWidth ? previousWidth : nextWidth)
    })

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return { ref, width }
}

function ActionButton({
  action,
  block = false,
}: {
  action: ResponsiveAction
  block?: boolean
}) {
  const button = (
    <Button
      className={block ? styles.moreButton : undefined}
      type={action.type ?? 'link'}
      size="small"
      danger={action.danger}
      disabled={action.disabled}
      loading={action.loading}
      icon={action.icon}
      onClick={action.confirm ? undefined : () => void action.onClick?.()}
    >
      {action.label}
    </Button>
  )

  if (!action.confirm) return button

  return (
    <Popconfirm
      {...action.confirm}
      onConfirm={() => void action.onClick?.()}
      disabled={action.disabled}
    >
      {button}
    </Popconfirm>
  )
}

export default function ResponsiveActions({
  actions,
  minInlineCount = 1,
}: ResponsiveActionsProps) {
  const visibleActions = actions.filter(Boolean)
  const { ref, width } = useElementWidth<HTMLDivElement>()

  const inlineCount = useMemo(() => {
    if (visibleActions.length <= minInlineCount) return visibleActions.length
    if (width <= 0) return visibleActions.length

    const allActionsWidth =
      visibleActions.length * ACTION_BUTTON_WIDTH + (visibleActions.length - 1) * ACTION_GAP
    if (width >= allActionsWidth) return visibleActions.length

    const remainingWidth = width - MORE_BUTTON_WIDTH - ACTION_GAP
    const count = Math.floor((remainingWidth + ACTION_GAP) / (ACTION_BUTTON_WIDTH + ACTION_GAP))
    return Math.min(
      visibleActions.length - 1,
      Math.max(minInlineCount, count),
    )
  }, [minInlineCount, visibleActions.length, width])

  const inlineActions = visibleActions.slice(0, inlineCount)
  const overflowActions = visibleActions.slice(inlineCount)
  const moreLoading = overflowActions.some((action) => action.loading)

  return (
    <div ref={ref} className={styles.actions}>
      {inlineActions.map((action) => (
        <ActionButton key={action.key} action={action} />
      ))}
      {overflowActions.length > 0 && (
        <Popover
          content={(
            <div className={styles.morePanel} role="menu">
              <div className={styles.moreMenu}>
                {overflowActions.map((action) => (
                  <ActionButton key={action.key} action={action} block />
                ))}
              </div>
            </div>
          )}
          placement="bottomRight"
          trigger="click"
        >
          <Button type="link" size="small" loading={moreLoading}>
            更多 <DownOutlined />
          </Button>
        </Popover>
      )}
    </div>
  )
}
