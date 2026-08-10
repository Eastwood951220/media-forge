import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { queryKeys } from './queryKeys'
import { invalidateCrawlerRunLists, invalidateCrawlerTaskLists } from './queryInvalidation'

describe('crawler query invalidation helpers', () => {
  it('invalidates crawler run list and count queries through the crawlerRuns root key', async () => {
    const client = new QueryClient()
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries').mockResolvedValue()

    await invalidateCrawlerRunLists(client)

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.crawlerRuns.all() })
  })

  it('invalidates crawler task list and count queries through the crawlerTasks root key', async () => {
    const client = new QueryClient()
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries').mockResolvedValue()

    await invalidateCrawlerTaskLists(client)

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.crawlerTasks.all() })
  })
})
