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
  roles: string[]
  permissions: string[]
  isAuthenticated: boolean
  hasUserInfo: boolean
  setLoginState: (token: string, userInfo?: UserInfo | null) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set) => ({
        token: getToken() ?? '',
        userInfo: null,
        roles: [],
        permissions: [],
        isAuthenticated: Boolean(getToken()),
        hasUserInfo: false,

        setLoginState: (token, userInfo) => {
          setToken(token)
          set({
            token,
            userInfo: userInfo ?? null,
            roles: [],
            permissions: [],
            isAuthenticated: true,
            hasUserInfo: Boolean(userInfo),
          })
        },

        logout: () => {
          removeToken()
          set({
            token: '',
            userInfo: null,
            roles: [],
            permissions: [],
            isAuthenticated: false,
            hasUserInfo: false,
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
