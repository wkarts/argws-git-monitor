import { clearAuthSession, readAuthSession, saveAuthSession, tokenPairToSession } from './auth-storage'
import type { TokenPair } from '../types/api'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  authenticated?: boolean
  retryOnUnauthorized?: boolean
}

let refreshPromise: Promise<boolean> | null = null

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const session = readAuthSession()
    if (!session?.refreshToken) return false
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: session.refreshToken })
      })
      if (!response.ok) {
        clearAuthSession()
        return false
      }
      const payload = (await response.json()) as TokenPair
      saveAuthSession(tokenPairToSession(payload))
      return true
    } catch {
      return false
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

async function parseError(response: Response): Promise<ApiError> {
  const rawBody = await response.text().catch(() => '')
  let detail: unknown = rawBody || undefined
  let message = rawBody || `Erro HTTP ${response.status}`

  if (rawBody) {
    try {
      detail = JSON.parse(rawBody) as unknown
      if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
        const responseDetail = (detail as { detail: unknown }).detail
        if (typeof responseDetail === 'string') message = responseDetail
        else if (Array.isArray(responseDetail)) {
          message = responseDetail
            .map((item) =>
              typeof item === 'object' && item !== null && 'msg' in item
                ? String((item as { msg: unknown }).msg)
                : String(item)
            )
            .join('; ')
        }
      }
    } catch {
      // Mantém a resposta textual quando o servidor não retorna JSON.
    }
  }
  return new ApiError(message, response.status, detail)
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    body,
    authenticated = true,
    retryOnUnauthorized = true,
    headers: customHeaders,
    ...requestInit
  } = options
  const headers = new Headers(customHeaders)
  const session = readAuthSession()
  if (authenticated && session?.accessToken) {
    headers.set('Authorization', `Bearer ${session.accessToken}`)
  }
  let requestBody: BodyInit | undefined
  if (body instanceof FormData || body instanceof URLSearchParams || typeof body === 'string') {
    requestBody = body
  } else if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    requestBody = JSON.stringify(body)
  }

  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 30000)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      headers,
      body: requestBody,
      signal: options.signal ?? controller.signal
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('A requisição excedeu o tempo limite.', 0)
    }
    throw new ApiError('Não foi possível comunicar com o servidor.', 0, error)
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (response.status === 401 && authenticated && retryOnUnauthorized) {
    const refreshed = await refreshSession()
    if (refreshed) return request<T>(path, { ...options, retryOnUnauthorized: false })
  }
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'GET' })
  },
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'POST', body })
  },
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'PATCH', body })
  },
  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'DELETE' })
  }
}
