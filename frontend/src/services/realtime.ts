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
const WATCHDOG_INTERVAL_MS = 15_000
const STALE_CONNECTION_MS = 55_000

let socket: WebSocket | null = null
let connectPromise: Promise<void> | null = null
let reconnectTimer: number | undefined
let watchdogTimer: number | undefined
let reconnectAttempt = 0
let explicitlyStopped = true
let state: State = 'stopped'
let generation = 0
let lastMessageAt = 0

function emitState(next: State): void {
  state = next
  window.dispatchEvent(
    new CustomEvent(STATE_EVENT_NAME, {
      detail: { state: next, lastMessageAt: lastMessageAt || null }
    })
  )
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

function stopWatchdog(): void {
  if (watchdogTimer !== undefined) {
    window.clearInterval(watchdogTimer)
    watchdogTimer = undefined
  }
}

function startWatchdog(): void {
  if (watchdogTimer !== undefined) return
  watchdogTimer = window.setInterval(() => {
    const current = socket
    if (!current || current.readyState !== WebSocket.OPEN || explicitlyStopped) return
    if (lastMessageAt && Date.now() - lastMessageAt > STALE_CONNECTION_MS) {
      socket = null
      current.close(4000, 'realtime-stale')
      scheduleReconnect()
    }
  }, WATCHDOG_INTERVAL_MS)
}

function scheduleReconnect(): void {
  if (explicitlyStopped || !navigator.onLine || !readAuthSession()?.accessToken) return
  if (reconnectTimer !== undefined) return
  reconnectAttempt += 1
  const base = Math.min(15_000, 750 * 2 ** Math.min(reconnectAttempt - 1, 5))
  const jitter = Math.floor(Math.random() * Math.min(750, base / 4))
  emitState('reconnecting')
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = undefined
    void connect()
  }, base + jitter)
}

function closeSocket(reason: string): void {
  if (!socket) return
  const current = socket
  socket = null
  try { current.close(1000, reason) } catch { /* conexão já encerrada */ }
}

async function connect(): Promise<void> {
  if (explicitlyStopped || socket || !navigator.onLine || !readAuthSession()?.accessToken) return
  if (connectPromise) return connectPromise

  const attemptGeneration = generation
  connectPromise = (async () => {
    emitState(reconnectAttempt > 0 ? 'reconnecting' : 'connecting')
    try {
      const ticket = await api.post<RealtimeTicket>('/realtime/ticket')
      if (
        explicitlyStopped
        || attemptGeneration !== generation
        || socket
        || !navigator.onLine
        || !readAuthSession()?.accessToken
      ) return

      const ws = new WebSocket(wsUrl(ticket.websocket_path, ticket.ticket))
      socket = ws

      ws.onopen = () => {
        if (socket !== ws) {
          ws.close(1000, 'superseded')
          return
        }
        reconnectAttempt = 0
        lastMessageAt = Date.now()
        clearReconnect()
        startWatchdog()
        emitState('connected')
      }
      ws.onmessage = (message) => {
        if (socket !== ws) return
        lastMessageAt = Date.now()
        try {
          const event = JSON.parse(String(message.data)) as RealtimeEvent
          window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: event }))
        } catch {
          // Um frame inválido é descartado; o canal saudável não é derrubado.
        }
      }
      ws.onerror = () => {
        // onclose é o único responsável pelo backoff para impedir reconexões duplas.
      }
      ws.onclose = () => {
        if (socket === ws) socket = null
        if (!explicitlyStopped) scheduleReconnect()
      }
    } catch {
      scheduleReconnect()
    } finally {
      connectPromise = null
    }
  })()
  return connectPromise
}

function handleOnline(): void {
  if (!explicitlyStopped) void connect()
}

function handleOffline(): void {
  generation += 1
  clearReconnect()
  closeSocket('offline')
  if (!explicitlyStopped) emitState('reconnecting')
}

export const realtime = {
  get state(): State {
    return state
  },
  get lastMessageAt(): number {
    return lastMessageAt
  },
  start(): void {
    if (!explicitlyStopped) {
      void connect()
      return
    }
    explicitlyStopped = false
    generation += 1
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    startWatchdog()
    void connect()
  },
  stop(): void {
    if (explicitlyStopped && !socket && !connectPromise) return
    explicitlyStopped = true
    generation += 1
    clearReconnect()
    stopWatchdog()
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    closeSocket('client-stop')
    reconnectAttempt = 0
    lastMessageAt = 0
    emitState('stopped')
  },
  syncAuthentication(): void {
    if (readAuthSession()?.accessToken) {
      if (explicitlyStopped) this.start()
      else void connect()
    } else if (!explicitlyStopped || socket || connectPromise) {
      this.stop()
    }
  }
}

export const REALTIME_EVENT = EVENT_NAME
export const REALTIME_STATE_EVENT = STATE_EVENT_NAME
