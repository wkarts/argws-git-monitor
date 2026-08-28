<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertTriangle, Bell, Check, CheckCheck, ChevronLeft, ChevronRight, ExternalLink, Info, RefreshCw, ShieldCheck, XCircle } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import { useToastStore } from '../stores/toast'
import type { MessageResponse, NotificationItem, PaginatedResponse } from '../types/api'

const toasts = useToastStore()
const notifications = ref<PaginatedResponse<NotificationItem> | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const unreadOnly = ref(false)
const page = ref(1)
let timer: number | undefined
const unreadCount = computed(() => notifications.value?.items.filter((item) => !item.read_at).length ?? 0)
const severityIcons = { info: Info, success: Check, warning: AlertTriangle, error: XCircle }

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  errorMessage.value = ''
  try { notifications.value = await api.get<PaginatedResponse<NotificationItem>>(`/notifications?page=${page.value}&page_size=30&unread_only=${unreadOnly.value}`) }
  catch (error) { if (!silent) errorMessage.value = error instanceof ApiError ? error.message : 'Falha ao carregar notificações.' }
  finally { if (!silent) loading.value = false }
}

async function markRead(item: NotificationItem): Promise<void> {
  if (item.read_at) { if (item.url) window.open(item.url, '_blank', 'noopener,noreferrer'); return }
  try {
    const updated = await api.post<NotificationItem>(`/notifications/${item.id}/read`)
    item.read_at = updated.read_at
    if (item.url) window.open(item.url, '_blank', 'noopener,noreferrer')
  } catch (error) { toasts.error('Não foi possível marcar como lida', error instanceof ApiError ? error.message : undefined) }
}

async function markAll(): Promise<void> {
  try { const result = await api.post<MessageResponse>('/notifications/read-all'); toasts.success(result.message); await load() }
  catch (error) { toasts.error('Não foi possível atualizar', error instanceof ApiError ? error.message : undefined) }
}
function setUnreadOnly(): void { page.value = 1; unreadOnly.value = !unreadOnly.value; void load() }
function goToPage(target: number): void { if (!notifications.value || target < 1 || target > notifications.value.pages) return; page.value = target; void load() }
onMounted(() => { void load(); timer = window.setInterval(() => void load(true), 60000) })
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div class="page-stack">
    <section class="page-heading"><div><span class="eyebrow">CENTRAL DE ALERTAS</span><h2>Notificações</h2><p>Falhas, recuperações, releases e eventos importantes dos projetos monitorados.</p></div><div class="button-row"><button class="button ghost small" :class="{ active: unreadOnly }" @click="setUnreadOnly"><Bell :size="15" />{{ unreadOnly ? 'Mostrando não lidas' : 'Somente não lidas' }}</button><button class="button secondary small" :disabled="!notifications?.items.length" @click="markAll"><CheckCheck :size="15" />Marcar todas</button></div></section>
    <section class="platform-notice"><ShieldCheck :size="20"/><div><strong>Dialogs internos e push preservado</strong><p>Confirmações, prompts e avisos de operação são renderizados pelo próprio Git Monitor. Push notifications permanecem como notificações nativas quando a permissão estiver concedida, além desta Central de Alertas e do contador da navegação.</p></div></section>
    <div v-if="loading" class="notification-skeletons"><div v-for="index in 8" :key="index" class="skeleton notification-skeleton" /></div>
    <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Não foi possível consultar os alertas" :message="errorMessage"><button class="button secondary small" @click="load()"><RefreshCw :size="15" />Tentar novamente</button></EmptyState>
    <template v-else-if="notifications">
      <section v-if="notifications.items.length" class="notification-center"><header><span><strong>{{ notifications.total }}</strong> registro(s)</span><span v-if="unreadCount"><strong>{{ unreadCount }}</strong> nesta página ainda não lida(s)</span></header><article v-for="item in notifications.items" :key="item.id" class="notification-item" :class="[`severity-${item.severity}`, { unread: !item.read_at }]" @click="markRead(item)"><div class="severity-icon"><component :is="severityIcons[item.severity]" :size="18" /></div><div class="notification-copy"><div><strong>{{ item.title }}</strong><span v-if="!item.read_at" class="new-badge">Novo</span></div><p>{{ item.message }}</p><small>{{ formatRelative(item.created_at) }} · {{ item.event_type }}</small></div><ExternalLink v-if="item.url" :size="16" class="external-icon" /><Check v-else-if="item.read_at" :size="16" class="read-icon" /></article></section>
      <EmptyState v-else :icon="Bell" title="Nenhum alerta encontrado" :message="unreadOnly ? 'Todas as notificações já foram lidas.' : 'Os eventos relevantes aparecerão aqui automaticamente.'" />
      <nav v-if="notifications.pages > 1" class="pagination"><button class="icon-button" :disabled="page <= 1" @click="goToPage(page - 1)"><ChevronLeft :size="18" /></button><span>Página <strong>{{ page }}</strong> de {{ notifications.pages }}</span><button class="icon-button" :disabled="page >= notifications.pages" @click="goToPage(page + 1)"><ChevronRight :size="18" /></button></nav>
    </template>
  </div>
</template>

<style scoped>
.button-row{display:flex;gap:.55rem;flex-wrap:wrap}.button.active{color:var(--primary-strong);border-color:color-mix(in srgb,var(--primary) 35%,var(--border));background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.platform-notice{display:grid;grid-template-columns:auto 1fr;align-items:start;gap:.8rem;padding:.9rem;color:var(--success);border:1px solid color-mix(in srgb,var(--success) 25%,var(--border));border-radius:var(--radius-lg);background:color-mix(in srgb,var(--success) 6%,var(--surface))}.platform-notice strong{color:var(--text-strong);font-size:.76rem}.platform-notice p{margin:.12rem 0 0;color:var(--text-muted);font-size:.68rem;line-height:1.5}.notification-center{overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--surface)}.notification-center>header{display:flex;justify-content:space-between;gap:1rem;padding:.7rem 1rem;color:var(--text-subtle);font-size:.65rem;border-bottom:1px solid var(--border);background:var(--surface-raised)}.notification-center>header strong{color:var(--text)}.notification-item{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.8rem;padding:.9rem 1rem;border-bottom:1px solid var(--border-soft);cursor:pointer;transition:background .15s ease}.notification-item:last-child{border-bottom:0}.notification-item:hover{background:var(--surface-raised)}.notification-item.unread{background:color-mix(in srgb,var(--primary) 4%,var(--surface))}.severity-icon{display:grid;place-items:center;width:2.35rem;height:2.35rem;color:var(--info);border-radius:.72rem;background:color-mix(in srgb,var(--info) 10%,var(--surface))}.severity-success .severity-icon{color:var(--success);background:color-mix(in srgb,var(--success) 10%,var(--surface))}.severity-warning .severity-icon{color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,var(--surface))}.severity-error .severity-icon{color:var(--danger);background:color-mix(in srgb,var(--danger) 10%,var(--surface))}.notification-copy{display:grid;min-width:0}.notification-copy>div{display:flex;align-items:center;gap:.45rem}.notification-copy strong{overflow:hidden;color:var(--text);font-size:.78rem;text-overflow:ellipsis;white-space:nowrap}.notification-copy p{margin:.18rem 0;color:var(--text-muted);font-size:.7rem;line-height:1.4}.notification-copy small{color:var(--text-subtle);font-size:.6rem}.new-badge{padding:.1rem .35rem;color:var(--primary-strong);font-size:.54rem;font-weight:800;border-radius:999px;background:color-mix(in srgb,var(--primary) 12%,var(--surface))}.external-icon{color:var(--text-subtle)}.read-icon{color:var(--success)}.notification-skeletons{display:grid;gap:.55rem}.notification-skeleton{height:78px}.pagination{display:flex;align-items:center;justify-content:center;gap:.8rem}.pagination span{color:var(--text-muted);font-size:.7rem}@media(max-width:700px){.notification-center>header{display:grid}.notification-item{grid-template-columns:auto 1fr}.notification-item>.external-icon,.notification-item>.read-icon{grid-column:2}.page-heading .button-row{width:100%}.page-heading .button{flex:1}}
</style>
