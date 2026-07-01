import { request } from '@/request'
import type { InitConfigRequest, InitConfigResponse } from './types'

export function getInitConfig(): Promise<InitConfigResponse> {
  return request<InitConfigResponse>({
    url: '/api/init/config',
    method: 'get',
    isToken: false,
  })
}

export function saveInitConfig(data: InitConfigRequest): Promise<InitConfigResponse> {
  return request<InitConfigResponse>({
    url: '/api/init/config',
    method: 'post',
    data,
    isToken: false,
  })
}
