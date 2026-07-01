import { request } from '@/request'
import type { LoginParams, LoginResult } from './types'

export function login(data: LoginParams): Promise<LoginResult> {
  return request<LoginResult>({
    url: '/api/auth/login',
    method: 'post',
    data,
    isToken: false,
    isRepeatSubmit: false,
  })
}

export function logout(): Promise<void> {
  return request({
    url: '/api/auth/logout',
    method: 'post',
  })
}
