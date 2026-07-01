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
