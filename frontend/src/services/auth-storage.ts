import type { AuthSession, TokenPair } from '../types/api'

const STORAGE_KEY = 'argws-git-monitor.auth'

export function tokenPairToSession(payload: TokenPair): AuthSession {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    accessExpiresAt: payload.access_expires_at,
    refreshExpiresAt: payload.refresh_expires_at,
    user: payload.user
  }
}

export function readAuthSession(): AuthSession | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (!value) return null
    const parsed = JSON.parse(value) as AuthSession
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.user) return null
    return parsed
  } catch {
    return null
  }
}

export function saveAuthSession(session: AuthSession): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  window.dispatchEvent(new CustomEvent<AuthSession>('argws-auth-updated', { detail: session }))
}

export function clearAuthSession(): void {
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new Event('argws-auth-cleared'))
}
