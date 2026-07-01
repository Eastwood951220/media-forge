import { useState, useCallback } from 'react'
import { Tabs } from 'antd'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { useSwipeTabs } from './useSwipeTabs'
import styles from './index.module.less'

type TabItem = {
  key: string
  label: string
  closable?: boolean
}

const DEFAULT_TABS: TabItem[] = [
  { key: '/dashboard', label: 'Dashboard', closable: false },
]

/**
 * TabsView component for displaying open page tabs.
 *
 * - Desktop: renders editable-card style tabs for navigation
 * - Mobile: returns null (tabs are hidden)
 */
export default function TabsView() {
  const { isMobile } = useBreakpoint()
  const [tabs, setTabs] = useState<TabItem[]>(DEFAULT_TABS)
  const [activeKey, setActiveKey] = useState('/dashboard')

  const handleEdit = useCallback<Required<React.ComponentProps<typeof Tabs>>['onEdit']>(
    (targetKey, action) => {
      if (action !== 'remove') return
      const keyToRemove = String(targetKey)
      setTabs((prev) => {
        const next = prev.filter((tab) => tab.key !== keyToRemove)
        // If removing active tab, switch to last remaining tab
        if (keyToRemove === activeKey && next.length > 0) {
          setActiveKey(next[next.length - 1]!.key)
        }
        return next
      })
    },
    [activeKey],
  )

  const handleChange = useCallback((key: string) => {
    setActiveKey(key)
  }, [])

  const swipeHandlers = useSwipeTabs({
    onSwipeLeft: () => {
      const currentIndex = tabs.findIndex((t) => t.key === activeKey)
      if (currentIndex < tabs.length - 1) {
        setActiveKey(tabs[currentIndex + 1]!.key)
      }
    },
    onSwipeRight: () => {
      const currentIndex = tabs.findIndex((t) => t.key === activeKey)
      if (currentIndex > 0) {
        setActiveKey(tabs[currentIndex - 1]!.key)
      }
    },
  })

  if (isMobile) {
    return null
  }

  return (
    <div className={styles.tabsView} {...swipeHandlers}>
      <Tabs
        type="editable-card"
        hideAdd
        activeKey={activeKey}
        items={tabs.map((tab) => ({
          key: tab.key,
          label: tab.label,
          closable: tab.closable ?? true,
        }))}
        onChange={handleChange}
        onEdit={handleEdit}
      />
    </div>
  )
}
