import type { AuthUser } from '@/lib/api/types'

const TOKEN_KEY = 'aurora_access_token'
const USER_KEY = 'aurora_auth_user'
const AUTH_CHANGE_EVENT = 'aurora-auth-change'

export type AuthSnapshot = {
  accessToken: string | null
  user: AuthUser | null
  authenticated: boolean
}

function emitAuthChange(): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<AuthSnapshot>(AUTH_CHANGE_EVENT, {
      detail: getAuthSnapshot(),
    }),
  )
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function getAuthUser(): AuthUser | null {
  if (typeof window === 'undefined') return null

  const raw = window.localStorage.getItem(USER_KEY)
  if (!raw) return null

  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    window.localStorage.removeItem(USER_KEY)
    return null
  }
}

export function getAuthSnapshot(): AuthSnapshot {
  const accessToken = getAccessToken()
  const user = getAuthUser()

  return {
    accessToken,
    user,
    authenticated: Boolean(accessToken),
  }
}

export function setAccessToken(token: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
  emitAuthChange()
}

export function setAuthUser(user: AuthUser): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(USER_KEY, JSON.stringify(user))
  emitAuthChange()
}

export function setAuthSession(token: string, user: AuthUser): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
  window.localStorage.setItem(USER_KEY, JSON.stringify(user))
  emitAuthChange()
}

export function clearAccessToken(): void {
  clearAuthSession()
}

export function clearAuthSession(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
  window.localStorage.removeItem(USER_KEY)
  emitAuthChange()
}

export function subscribeAuthChange(listener: (snapshot: AuthSnapshot) => void): () => void {
  if (typeof window === 'undefined') {
    return () => undefined
  }

  const handleCustomEvent = (event: Event) => {
    const detail = (event as CustomEvent<AuthSnapshot>).detail
    listener(detail ?? getAuthSnapshot())
  }

  const handleStorageEvent = (event: StorageEvent) => {
    if (event.key === TOKEN_KEY || event.key === USER_KEY || event.key === null) {
      listener(getAuthSnapshot())
    }
  }

  window.addEventListener(AUTH_CHANGE_EVENT, handleCustomEvent)
  window.addEventListener('storage', handleStorageEvent)

  return () => {
    window.removeEventListener(AUTH_CHANGE_EVENT, handleCustomEvent)
    window.removeEventListener('storage', handleStorageEvent)
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken())
}
