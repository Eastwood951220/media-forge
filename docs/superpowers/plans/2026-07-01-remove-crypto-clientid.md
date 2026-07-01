# Remove Crypto & clientId from src/request/ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip all encryption-related code and `clientId` header injection from `frontend/src/request/`, removing one file entirely and cleaning six others.

**Architecture:** The `crypto.ts` file is a self-contained module for AES+RSA request/response encryption — it and all its consumers are removed. `clientId` is a per-request header injected from env vars — it and its injection sites are removed. The rest of the request pipeline (token auth, caching, cancel, repeat-submit, transform) stays intact.

**Tech Stack:** TypeScript, Axios

## Global Constraints

- `crypto.ts` file deleted entirely
- All references to `clientId`, `CLIENT_ID_HEADER`, `isEncrypt`, `encryptRequestData`, `decryptResponseData` removed
- `import { decryptResponseData, encryptRequestData } from './crypto'` removed from all files
- `import { clientId } from './instance'` removed from `index.ts`
- No TypeScript errors, no ESLint errors after cleanup
- No net-new code — deletion only
- `crypto-js` and `jsencrypt` npm packages remain (may be used elsewhere in codebase)

---

### Task 1: Delete `crypto.ts`

**Files:**
- Delete: `frontend/src/request/crypto.ts`

**Interfaces:**
- Produces: `crypto.ts` no longer exists. Any remaining imports of it will cause tsc errors (fixed in Task 4).

- [ ] **Step 1: Delete the file**

```bash
rm /Users/eastwood/Code/PycharmProjects/media-forge/frontend/src/request/crypto.ts
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/crypto.ts
git commit -m "refactor: remove crypto.ts encryption module"
```

---

### Task 2: Remove `clientId` from `instance.ts`

**Files:**
- Modify: `frontend/src/request/instance.ts`

**Interfaces:**
- Consumes: (none)
- Produces: `instance.ts` exports only `baseURL` and `service` — no `clientId`

- [ ] **Step 1: Rewrite instance.ts**

Replace the entire file content:

Current:
```typescript
import axios from 'axios'

const CLIENT_ID_HEADER = 'clientid'

export const baseURL = import.meta.env.VITE_APP_BASE_API || ''
export const clientId = import.meta.env.VITE_APP_CLIENT_ID || ''

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'

if (clientId) {
  axios.defaults.headers[CLIENT_ID_HEADER] = clientId
}

export const service = axios.create({
  baseURL,
  timeout: 50000,
  headers: {
    'Content-Type': 'application/json;charset=utf-8',
    ...(clientId ? { [CLIENT_ID_HEADER]: clientId } : {}),
  },
  transitional: {
    clarifyTimeoutError: true,
  },
})
```

New:
```typescript
import axios from 'axios'

export const baseURL = import.meta.env.VITE_APP_BASE_API || ''

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'

export const service = axios.create({
  baseURL,
  timeout: 50000,
  headers: {
    'Content-Type': 'application/json;charset=utf-8',
  },
  transitional: {
    clarifyTimeoutError: true,
  },
})
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/instance.ts
git commit -m "refactor: remove clientId from instance.ts"
```

---

### Task 3: Remove `isEncrypt` from `types.ts`

**Files:**
- Modify: `frontend/src/request/types.ts:24-25`

**Interfaces:**
- Consumes: (none)
- Produces: `RequestConfig` no longer has `isEncrypt` field

- [ ] **Step 1: Remove the `isEncrypt` field**

Delete lines 24-25:
```
	  /** true 时对 POST/PUT 请求体执行 AES + RSA 加密。 */
	  isEncrypt?: boolean
```

The surrounding context (lines 21-39):
```typescript
	  /** 单接口自定义重复提交间隔。 */
	  repeatSubmitInterval?: number

	  /** true 时对 POST/PUT 请求体执行 AES + RSA 加密。 */
	  isEncrypt?: boolean

	  /** true 时直接返回 AxiosResponse。 */
	  isReturnNativeResponse?: boolean
```

After removal:
```typescript
	  /** 单接口自定义重复提交间隔。 */
	  repeatSubmitInterval?: number

	  /** true 时直接返回 AxiosResponse。 */
	  isReturnNativeResponse?: boolean
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/types.ts
git commit -m "refactor: remove isEncrypt from RequestConfig"
```

---

### Task 4: Remove crypto + clientId from `interceptors.ts`

**Files:**
- Modify: `frontend/src/request/interceptors.ts`

**Interfaces:**
- Consumes: (no more imports from `./crypto`; no more `clientId` variable)
- Produces: Interceptors no longer encrypt/decrypt or inject clientId

- [ ] **Step 1: Remove crypto import (line 6)**

Delete:
```typescript
import { decryptResponseData, encryptRequestData } from './crypto'
```

- [ ] **Step 2: Remove CLIENT_ID_HEADER and clientId (lines 20-21)**

Delete:
```typescript
const CLIENT_ID_HEADER = 'clientid'
const clientId = import.meta.env.VITE_APP_CLIENT_ID || ''
```

- [ ] **Step 3: Remove clientId injection block (lines 36-39)**

Delete:
```typescript
	      // clientid 注入
	      if (clientId) {
	        requestConfig.headers.set(CLIENT_ID_HEADER, clientId)
	      }
```

- [ ] **Step 4: Remove encryptRequestData call (line 50)**

Delete:
```typescript
	      // 请求加密
	      encryptRequestData(requestConfig)
```

- [ ] **Step 5: Remove decryptResponseData call (lines 92-93)**

Delete:
```typescript
	      // 响应解密
	      decryptResponseData(response)
```

- [ ] **Step 6: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/interceptors.ts
git commit -m "refactor: remove crypto and clientId from interceptors"
```

---

### Task 5: Remove `isEncrypt` from `clearInternalHeaders` in `utils.ts`

**Files:**
- Modify: `frontend/src/request/utils.ts:169`

**Interfaces:**
- Consumes: (none)
- Produces: `clearInternalHeaders` no longer strips `isEncrypt` header

- [ ] **Step 1: Remove `'isEncrypt'` from the array**

Line 169 currently:
```typescript
  ;['isToken', 'repeatSubmit', 'interval', 'isEncrypt'].forEach((key) => {
```

Change to:
```typescript
  ;['isToken', 'repeatSubmit', 'interval'].forEach((key) => {
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/utils.ts
git commit -m "refactor: remove isEncrypt from clearInternalHeaders"
```

---

### Task 6: Remove `clientId` from `index.ts`

**Files:**
- Modify: `frontend/src/request/index.ts:5,21`

**Interfaces:**
- Produces: `index.ts` no longer imports or uses `clientId`

- [ ] **Step 1: Remove clientId from import (line 5)**

Change line 5 from:
```typescript
import {clientId, service} from './instance'
```
To:
```typescript
import {service} from './instance'
```

- [ ] **Step 2: Remove clientId from globalHeaders (line 21)**

Change `globalHeaders` from:
```typescript
export function globalHeaders(): Record<string, string> {
  const token = getToken()

  return {
    ...(token ? {[AUTHORIZATION_HEADER]: `Bearer ${token}`} : {}),
    ...(clientId ? {clientid: clientId} : {}),
  }
}
```
To:
```typescript
export function globalHeaders(): Record<string, string> {
  const token = getToken()

  return {
    ...(token ? {[AUTHORIZATION_HEADER]: `Bearer ${token}`} : {}),
  }
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -f src/request/index.ts
git commit -m "refactor: remove clientId from index.ts"
```

---

### Task 7: Final verification

**Files:** (none — verification only)

- [ ] **Step 1: Run TypeScript check**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx tsc -b
```

Expected: Zero type errors. If errors exist (e.g., other files importing `clientId` or crypto functions), fix by removing those imports too.

- [ ] **Step 2: Run ESLint**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npx eslint src/request/
```

Expected: Zero errors.

- [ ] **Step 3: Run build and tests**

```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend && npm run build 2>&1 | tail -3 && npx vitest run 2>&1 | tail -3
```

Expected: Build succeeds, all tests pass.

- [ ] **Step 4: Commit any fixes**

If fixes were needed, commit them:
```bash
cd /Users/eastwood/Code/PycharmProjects/media-forge/frontend
git add -A
git commit -m "chore: final verification after crypto and clientId removal"
```
