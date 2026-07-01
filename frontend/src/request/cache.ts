const DEFAULT_CACHE_TIME = 5 * 60 * 1000

type CacheRecord<T = unknown> = {
  data: T
  expireTime: number
}

const cacheMap = new Map<string, CacheRecord>()

export function getRequestCache<T = unknown>(key: string): T | undefined {
  const record = cacheMap.get(key)

  if (!record) {
    return undefined
  }

  if (Date.now() > record.expireTime) {
    cacheMap.delete(key)
    return undefined
  }

  return record.data as T
}

export function setRequestCache<T = unknown>(
  key: string,
  data: T,
  cacheTime?: number,
): void {
  cacheMap.set(key, {
    data,
    expireTime: Date.now() + (cacheTime ?? DEFAULT_CACHE_TIME),
  })
}

export function removeRequestCache(key: string): void {
  cacheMap.delete(key)
}

export function clearRequestCache(): void {
  cacheMap.clear()
}
