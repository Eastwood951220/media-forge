import {getToken} from '@/utils/auth'

const AUTHORIZATION_HEADER = 'Authorization'

export function globalHeaders(): Record<string, string> {
    const token = getToken()

    return {
        ...(token ? {[AUTHORIZATION_HEADER]: `Bearer ${token}`} : {}),
    }
}
