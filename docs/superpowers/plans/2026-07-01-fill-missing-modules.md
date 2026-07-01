# Fill Missing Modules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the 4 missing modules (`@/enums/RespEnum`, `@/utils/auth`, `@/utils/cache`, `@/store/useAuthStore`) that the `src/request/` layer depends on, adapted from the ruoyi-react reference project.

**Architecture:** Each module is self-contained with no cross-dependencies (except `useAuthStore` → `utils/auth`). Adapted from ruoyi-react with unnecessary external dependencies stripped (no `@/api/*`, no `@/store/usePermissionStore`, no `@/store/useTagsViewStore`). `useAuthStore` is simplified: keeps token management and logout, defers `loadUserInfo` to a later task.

**Tech Stack:** TypeScript, Zustand 5, js-cookie

## Reference Source

All implementations are adapted from: `/Users/eastwood/Code/WebstormProjects/ruoyi-react/src/`

---

### Task 1: Create `src/enums/RespEnum.ts`

**Files:**
- Create: `frontend/src/enums/RespEnum.ts`

**Interfaces:**
- Produces: `HttpStatus` — const object with `SUCCESS`, `UNAUTHORIZED`, `SERVER_ERROR`, `WARN`
- Consumed by: `src/request/transform.ts` line 3

- [ ] **Step 1: Write the file**

```typescript
export const HttpStatus = {
  SUCCESS: 200,
  UNAUTHORIZED: 401,
  SERVER_ERROR: 500,
  WARN: 601,
} as const
```

- [ ] **Step 2: Verify tsc resolves the import**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | grep -c "RespEnum"
```

Expected: `0` (no errors referencing RespEnum).

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/enums/RespEnum.ts
git commit -m "feat: add HttpStatus enum constants"
```

---

### Task 2: Create `src/utils/cache.ts`

**Files:**
- Create: `frontend/src/utils/cache.ts`

**Interfaces:**
- Produces:
  - `sessionCache: CacheStorage` (backed by `sessionStorage`)
  - `localCache: CacheStorage` (backed by `localStorage`)
  - `default export: { session: sessionCache, local: localCache }`
- Consumed by: `src/request/repeatSubmit.ts` line 2 — `import cache from '@/utils/cache'` → uses `cache.session.getJSON()` and `cache.session.setJSON()`

- [ ] **Step 1: Write the file**

```typescript
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
```

- [ ] **Step 2: Verify tsc resolves the import**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | grep -c "cache"
```

Expected: `0` (no errors referencing `@/utils/cache`).

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/utils/cache.ts
git commit -m "feat: add cache utility (sessionStorage/localStorage wrapper)"
```

---

### Task 3: Create `src/utils/auth.ts`

**Files:**
- Create: `frontend/src/utils/auth.ts`

**Interfaces:**
- Produces: `getToken(): string | null`, `setToken(token: string): void`, `removeToken(): void`
- Consumed by: `src/request/index.ts` line 1 (`getToken`), `src/request/interceptors.ts` line 2 (`getToken`)
- Dependencies: `js-cookie` (already in `package.json` dependencies)

- [ ] **Step 1: Write the file**

```typescript
import Cookies from 'js-cookie'

const TOKEN_KEY = 'Admin-Token'

export function getToken(): string | null {
  return Cookies.get(TOKEN_KEY) ?? null
}

export function setToken(token: string): void {
  Cookies.set(TOKEN_KEY, token)
}

export function removeToken(): void {
  Cookies.remove(TOKEN_KEY)
}
```

- [ ] **Step 2: Verify tsc resolves the import**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | grep -c "@/utils/auth"
```

Expected: `0`.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/utils/auth.ts
git commit -m "feat: add auth utility (token via js-cookie)"
```

---

### Task 4: Create `src/store/useAuthStore.ts`

**Files:**
- Create: `frontend/src/store/useAuthStore.ts`

**Interfaces:**
- Consumes: `getToken`, `setToken`, `removeToken` from `@/utils/auth` (Task 3)
- Produces: `useAuthStore` — Zustand store with `token`, `setLoginState`, `logout`
- Consumed by: `src/request/transform.ts` line 4 — calls `useAuthStore.getState().logout()`

**Simplified from ruoyi-react:** Removes dependencies on `@/api/system/user` (loadUserInfo), `@/store/usePermissionStore`, `@/store/useTagsViewStore`. The `loadUserInfo` function is kept as a stub that throws if called before the API module exists.

- [ ] **Step 1: Write the file**

```typescript
import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { getToken, removeToken, setToken } from '@/utils/auth'

type UserInfo = {
  userId?: number | string
  username: string
  displayName: string
  avatar?: string
}

type AuthState = {
  token: string
  userInfo: UserInfo | null
  roles: string[]
  permissions: string[]
  isAuthenticated: boolean
  hasUserInfo: boolean
  setLoginState: (token: string, userInfo?: UserInfo | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set) => ({
        token: getToken() ?? '',
        userInfo: null,
        roles: [],
        permissions: [],
        isAuthenticated: Boolean(getToken()),
        hasUserInfo: false,

        setLoginState: (token, userInfo) => {
          setToken(token)
          set({
            token,
            userInfo: userInfo ?? null,
            roles: [],
            permissions: [],
            isAuthenticated: true,
            hasUserInfo: Boolean(userInfo),
          })
        },

        logout: () => {
          removeToken()
          set({
            token: '',
            userInfo: null,
            roles: [],
            permissions: [],
            isAuthenticated: false,
            hasUserInfo: false,
          })
        },
      }),
      {
        name: 'media-forge-auth',
        partialize: (state) => ({
          token: state.token,
          isAuthenticated: state.isAuthenticated,
        }),
      },
    ),
  ),
)
```

- [ ] **Step 2: Verify tsc resolves all imports**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b 2>&1 | head -20
```

Expected: Zero errors related to `@/store/useAuthStore`.

- [ ] **Step 3: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/store/useAuthStore.ts
git commit -m "feat: add auth store (Zustand with persist)"
```

---

### Task 5: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run full verification**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
npx tsc -b && echo "✅ TSC"
npx eslint . && echo "✅ LINT"
npm run build && echo "✅ BUILD"
npx vitest run && echo "✅ TEST"
```

Expected: All four pass. Zero TypeScript errors (the 4 missing module errors should be gone).

- [ ] **Step 2: Commit if any fix was needed**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -A
git commit -m "chore: final verification after filling missing modules"
```
