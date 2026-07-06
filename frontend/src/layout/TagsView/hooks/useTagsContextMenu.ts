import { useCallback, useEffect, useState } from 'react'
import type { TagView } from '@/stores/useTagsViewStore'
import { clampContextMenuPosition } from '../tagsViewUtils'

export type ContextMenuState = {
  visible: boolean
  left: number
  top: number
  selectedTag?: TagView
}

export function useTagsContextMenu() {
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    left: 0,
    top: 0,
  })

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => (prev.visible ? { ...prev, visible: false } : prev))
  }, [])

  useEffect(() => {
    document.addEventListener('click', closeContextMenu)
    return () => document.removeEventListener('click', closeContextMenu)
  }, [closeContextMenu])

  const handleContextMenu = useCallback((tag: TagView, event: React.MouseEvent) => {
    event.preventDefault()
    const menuWidth = 140
    const menuHeight = 260
    const { left, top } = clampContextMenuPosition(
      event.clientX,
      event.clientY,
      menuWidth,
      menuHeight,
      window.innerWidth,
      window.innerHeight,
    )

    setContextMenu({
      visible: true,
      left,
      top,
      selectedTag: tag,
    })
  }, [])

  return { contextMenu, closeContextMenu, handleContextMenu }
}
