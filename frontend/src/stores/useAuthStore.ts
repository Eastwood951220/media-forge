import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { getToken, removeToken, setToken } from '@/utils/auth.ts'

type UserInfo = {
  userId?: number | string
  username: string
  displayName: string
  avatar?: string
}

type AuthState = {
  token: string
  userInfo: UserInfo | null
  isAuthenticated: boolean
  setLoginState: (token: string, userInfo?: UserInfo | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set) => ({
        token: getToken() ?? '',
        userInfo: null,
        isAuthenticated: Boolean(getToken()),

        setLoginState: (token, userInfo) => {
          setToken(token)
          set({
            token,
            userInfo: userInfo ?? null,
            isAuthenticated: true,
          })
        },

        logout: () => {
          removeToken()
          set({
            token: '',
            userInfo: null,
            isAuthenticated: false,
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

/** Check if user is logged in — token from cookie must exist AND state must agree. */
export function isLoggedIn(): boolean {
  const { token, isAuthenticated } = useAuthStore.getState()
  return Boolean(token) && isAuthenticated
}
