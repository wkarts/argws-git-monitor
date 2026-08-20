import type { HealthStatus, NotificationSeverity } from '../types/api'

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Não informado'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Data inválida'
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(date)
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return 'sem registro'
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) return 'data inválida'
  const seconds = Math.round((timestamp - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('pt-BR', { numeric: 'auto' })
  const absolute = Math.abs(seconds)
  if (absolute < 60) return formatter.format(seconds, 'second')
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return formatter.format(hours, 'hour')
  const days = Math.round(hours / 24)
  if (Math.abs(days) < 30) return formatter.format(days, 'day')
  const months = Math.round(days / 30)
  if (Math.abs(months) < 12) return formatter.format(months, 'month')
  return formatter.format(Math.round(months / 12), 'year')
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  if (minutes < 60) return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

export function shortSha(value: string | null | undefined): string {
  return value?.slice(0, 8) || '—'
}

export function healthLabel(status: HealthStatus): string {
  const labels: Record<HealthStatus, string> = {
    healthy: 'Saudável',
    running: 'Executando',
    attention: 'Atenção',
    failing: 'Falhando',
    unknown: 'Sem CI'
  }
  return labels[status]
}

export function conclusionLabel(value: string | null | undefined): string {
  const labels: Record<string, string> = {
    success: 'Sucesso',
    failure: 'Falhou',
    cancelled: 'Cancelado',
    timed_out: 'Tempo esgotado',
    action_required: 'Ação necessária',
    neutral: 'Neutro',
    skipped: 'Ignorado',
    stale: 'Obsoleto',
    completed: 'Concluído',
    in_progress: 'Executando',
    queued: 'Na fila',
    requested: 'Solicitado',
    waiting: 'Aguardando',
    pending: 'Pendente'
  }
  if (!value) return 'Desconhecido'
  return labels[value] ?? value.replaceAll('_', ' ')
}

export function severityIcon(severity: NotificationSeverity): string {
  return { info: 'i', success: '✓', warning: '!', error: '×' }[severity]
}
