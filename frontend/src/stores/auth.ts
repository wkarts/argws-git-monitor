import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../services/api'
import {
  clearAuthSession,
  readAuthSession,
  saveAuthSession,
  tokenPairToSession
} from '../services/auth-storage'
import type { AuthSession, MessageResponse, TokenPair, User } from '../types/api'

export const useAuthStore = defineStore('auth', () => {
  const session = ref<AuthSession | null>(readAuthSession())
  const initialized = ref(false)
  const busy = ref(false)

  const user = computed(() => session.value?.user ?? null)
  const isAuthenticated = computed(() => Boolean(session.value?.accessToken && user.value))

  function updateFromStorage(): void {
    session.value = readAuthSession()
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('argws-auth-updated', updateFromStorage)
    window.addEventListener('argws-auth-cleared', updateFromStorage)
  }

  async function initialize(): Promise<void> {
    if (initialized.value) return
    if (!session.value) {
      initialized.value = true
      return
    }
    try {
      const currentUser = await api.get<User>('/auth/me')
      session.value = { ...session.value, user: currentUser }
      saveAuthSession(session.value)
    } catch {
      clearAuthSession()
      session.value = null
    } finally {
      initialized.value = true
    }
  }

  async function login(email: string, password: string): Promise<User> {
    busy.value = true
    try {
      const payload = await api.post<TokenPair>(
        '/auth/login',
        { email, password },
        { authenticated: false, retryOnUnauthorized: false }
      )
      session.value = tokenPairToSession(payload)
      saveAuthSession(session.value)
      return payload.user
    } finally {
      busy.value = false
    }
  }

  async function logout(): Promise<void> {
    const refreshToken = session.value?.refreshToken
    try {
      if (refreshToken) {
        await api.post<MessageResponse>(
          '/auth/logout',
          { refresh_token: refreshToken },
          { retryOnUnauthorized: false }
        )
      }
    } finally {
      clearAuthSession()
      session.value = null
    }
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<string> {
    const response = await api.post<MessageResponse>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword
    })
    clearAuthSession()
    session.value = null
    return response.message
  }

  return {
    session,
    user,
    initialized,
    busy,
    isAuthenticated,
    initialize,
    login,
    logout,
    changePassword
  }
})
