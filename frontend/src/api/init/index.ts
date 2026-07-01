import { request } from '@/request'
import type {
  ConnectionTestResult,
  InitConfigRequest,
  InitConfigResponse,
  PostgresTestParams,
  RedisTestParams,
} from './types'

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

export function testPostgres(params: PostgresTestParams): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>({
    url: '/api/init/test-postgres',
    method: 'post',
    data: params,
    isToken: false,
  })
}

export function testRedis(params: RedisTestParams): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>({
    url: '/api/init/test-redis',
    method: 'post',
    data: params,
    isToken: false,
  })
}
