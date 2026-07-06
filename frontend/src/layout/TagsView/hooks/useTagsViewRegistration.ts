import { useEffect } from 'react'
import { useTagsViewStore } from '@/stores/useTagsViewStore'
import { TAGS_VIEW_WHITELIST } from '../tagsViewUtils'

export function useTagsViewRegistration({
  cacheKey,
  currentMeta,
  fullPath,
  pathname,
  searchStr,
}: {
  cacheKey: string
  currentMeta: { title: string; affix?: boolean }
  fullPath: string
  pathname: string
  searchStr: string
}): void {
  const addVisitedView = useTagsViewStore((state) => state.addVisitedView)

  useEffect(() => {
    // Skip whitelisted paths
    if (TAGS_VIEW_WHITELIST.includes(pathname)) {
      return
    }

    addVisitedView({
      path: pathname,
      fullPath,
      cacheKey,
      title: currentMeta.title,
      closable: pathname !== '/' && !currentMeta.affix,
      query: searchStr ? Object.fromEntries(new URLSearchParams(searchStr)) : undefined,
    })
  }, [addVisitedView, cacheKey, currentMeta, fullPath, pathname, searchStr])
}
