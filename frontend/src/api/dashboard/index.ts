import { request } from '@/request'
import type { DashboardOverview } from './types'

export type { DashboardOverview } from './types'

export function getDashboardOverview(): Promise<DashboardOverview> {
  return request.get<DashboardOverview>('/api/dashboard/overview')
}
