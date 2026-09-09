import { request } from '@/request'
import type {
  ActressFetchFromTaskPayload,
  ActressFetchFromTaskResult,
  ActressListResponse,
  ActressProfile,
  ActressProfileDetail,
  ActressQueryParams,
} from './types'

export type {
  ActressFetchFromTaskPayload,
  ActressFetchFromTaskResult,
  ActressListResponse,
  ActressProfile,
  ActressProfileDetail,
  ActressQueryParams,
  ActressRecentMovie,
} from './types'

const BASE_URL = '/api/content/actresses'

interface PaginatedActresses {
  rows: ActressProfile[]
  total: number
}

export function fetchActresses(params: ActressQueryParams): Promise<ActressListResponse> {
  return request.get<PaginatedActresses>(BASE_URL, params).then((res) => {
    const page = params.page ?? 1
    const limit = params.limit ?? 24
    return {
      items: res.rows,
      total: res.total,
      page,
      limit,
      total_pages: Math.max(1, Math.ceil(res.total / limit)),
    }
  })
}

export function fetchActress(id: string): Promise<ActressProfileDetail> {
  return request.get<ActressProfileDetail>(`${BASE_URL}/${id}`)
}

export function fetchActressesFromTask(payload: ActressFetchFromTaskPayload): Promise<ActressFetchFromTaskResult> {
  return request.post<ActressFetchFromTaskResult>(`${BASE_URL}/fetch-from-task`, payload)
}
