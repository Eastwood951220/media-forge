import { Modal } from 'antd'
import { useAuthStore } from '@/stores/useAuthStore.ts'

/**
 * 是否已经展示重新登录弹窗。
 *
 * 使用对象而不是 boolean，保留外部可读写形态；
 * 多个接口同时返回 401 时，只允许第一个接口触发确认框。
 */
export const isRelogin = { show: false }

export function loginRedirectUrl(): string {
  const current = `${window.location.pathname}${window.location.search}`
  const params = new URLSearchParams()
  if (current && current !== '/login') {
    params.set('redirect', current)
  }
  const query = params.toString()
  return query ? `/login?${query}` : '/login'
}

export function expireSession(msg: string): Promise<never> {
  useAuthStore.getState().logout()

  if (!isRelogin.show) {
    isRelogin.show = true
    Modal.confirm({
      title: '系统提示',
      content: '登录状态已过期，请重新登录。',
      okText: '重新登录',
      cancelText: '取消',
      onOk: () => {
        isRelogin.show = false
        window.location.href = loginRedirectUrl()
      },
      onCancel: () => {
        isRelogin.show = false
      },
    })
  }

  return Promise.reject(new Error(msg))
}
