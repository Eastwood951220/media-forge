# Task 7: Library Utilities

**Status:** Done

## Files Created

- `frontend/src/lib/axios.ts` — Axios instance with base `/api` URL, 30s timeout, JSON content type, and request/response interceptor stubs for auth and error handling.
- `frontend/src/lib/query-client.ts` — React Query `QueryClient` with 5-minute stale time, single retry on queries, no retry on mutations, and `refetchOnWindowFocus` disabled.

## Dependencies Required

- `axios`
- `@tanstack/react-query`
