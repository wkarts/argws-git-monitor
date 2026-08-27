import { api } from './api'
import { readAuthSession } from './auth-storage'

export interface RealtimeEvent<T = Record<string, unknown>> {
  type: string
  occurred_at: string
  repository_id: string | null
  correlation_id: string | null
  data: T
}

interface RealtimeTicket {
  ticket: string
  expires_in: number
  websocket_path: string
}

type State = 'stopped' | 'connecting' | 'connected' | 'reconnecting'

const EVENT_NAME = 'argws:realtime'
const STATE_EVENT_NAME = 'argws:realtime-state'

let socket: WebSocket | null = null
let reconnectTimer: number | undefined
let reconnectAttempt = 0
let explicitlyStopped = true
let state: State = 'stopped'

function emitState(next: State): void {
  state = next
  window.dispatchEvent(new CustomEvent(STATE_EVENT_NAME, { detail: { state: next } }))
}

function wsUrl(path: string, ticket: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = new URL(path, `${protocol}//${window.location.host}`)
  url.searchParams.set('ticket', ticket)
  return url.toString()
}

function clearReconnect(): void {
  if (reconnectTimer !== undefined) {
    window.clearTimeout(reconnectTimer)
    reconnectTimer = undefined
  }
}

function scheduleReconnect(): void {
  if (explicitlyStopped || !navigator.onLine || !readAuthSession()?.accessToken) return
  clearReconnect()
  reconnectAttempt += 1
  const base = Math.min(30_000, 1_000 * 2 ** Math.min(reconnectAttempt - 1, 5))
  const jitter = Math.floor(Math.random() * Math.min(1_000, base / 4))
  emitState('reconnecting')
  reconnectTimer = window.setTimeout(() => void connect(), base + jitter)
}

async function connect(): Promise<void> {
  if (explicitlyStopped || socket || !navigator.onLine || !readAuthSession()?.accessToken) return
  emitState(reconnectAttempt > 0 ? 'reconnecting' : 'connecting')
  try {
    const ticket = await api.post<RealtimeTicket>('/realtime/ticket')
    if (explicitlyStopped) return
    const ws = new WebSocket(wsUrl(ticket.websocket_path, ticket.ticket))
    socket = ws

    ws.onopen = () => {
      reconnectAttempt = 0
      emitState('connected')
    }
    ws.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as RealtimeEvent
        window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: event }))
      } catch {
        // Ignora quadros inválidos sem derrubar o canal realtime.
      }
    }
    ws.onerror = () => {
      // onclose agenda a reconexão e evita tentativas duplicadas.
    }
    ws.onclose = () => {
      if (socket === ws) socket = null
      scheduleReconnect()
    }
  } catch {
    scheduleReconnect()
  }
}

function handleOnline(): void {
  if (!explicitlyStopped) void connect()
}

function handleOffline(): void {
  clearReconnect()
  if (socket) {
    const current = socket
    socket = null
    current.close(1000, 'offline')
  }
  if (!explicitlyStopped) emitState('reconnecting')
}

export const realtime = {
  get state(): State {
    return state
  },
  start(): void {
    explicitlyStopped = false
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    void connect()
  },
  stop(): void {
    explicitlyStopped = true
    clearReconnect()
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    if (socket) {
      const current = socket
      socket = null
      current.close(1000, 'client-stop')
    }
    reconnectAttempt = 0
    emitState('stopped')
  },
  syncAuthentication(): void {
    if (readAuthSession()?.accessToken) {
      if (explicitlyStopped) this.start()
      else void connect()
    } else if (!explicitlyStopped || socket) {
      this.stop()
    }
  }
}

export const REALTIME_EVENT = EVENT_NAME
export const REALTIME_STATE_EVENT = STATE_EVENT_NAME
