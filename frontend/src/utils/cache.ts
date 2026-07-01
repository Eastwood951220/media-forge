interface CacheStorage {
  set(key: string, value: string): void
  get(key: string): string | null
  setJSON<T>(key: string, jsonValue: T): void
  getJSON<T>(key: string): T | null
  remove(key: string): void
}

function createCacheStorage(storage: Storage): CacheStorage {
  return {
    set(key: string, value: string): void {
      if (key != null && value != null) {
        storage.setItem(key, value)
      }
    },

    get(key: string): string | null {
      if (key == null) {
        return null
      }
      return storage.getItem(key)
    },

    setJSON<T>(key: string, jsonValue: T): void {
      if (jsonValue != null) {
        this.set(key, JSON.stringify(jsonValue))
      }
    },

    getJSON<T>(key: string): T | null {
      const value = this.get(key)
      if (value == null) {
        return null
      }
      try {
        return JSON.parse(value) as T
      } catch {
        this.remove(key)
        return null
      }
    },

    remove(key: string): void {
      storage.removeItem(key)
    },
  }
}

export const sessionCache = createCacheStorage(window.sessionStorage)
export const localCache = createCacheStorage(window.localStorage)

export default {
  session: sessionCache,
  local: localCache,
}
