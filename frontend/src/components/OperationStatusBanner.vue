<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, RefreshCw, ServerCrash } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import { useToastStore } from '../stores/toast'
import type { GitHubConnection, OperationModuleStatus, OperationsStatus, SyncResponse } from '../types/api'

const props = defineProps<{ moduleKey: 'actions' | 'pull_requests' | 'issues' | 'releases' }>()
const emit = defineEmits<{ refreshed: [] }>()
const toasts = useToastStore()
const status = ref<OperationsStatus | null>(null)
const syncing = ref(false)
let timer: number | undefined
let realtimeTimer: number | undefined

const module = computed<OperationModuleStatus | null>(() =>
  status.value?.modules.find((item) => item.key === props.moduleKey) || null
)
const coverage = computed(() => {
  if (!module.value?.monitored_repositories) return 0
  return Math.round((module.value.observed_repositories / module.value.monitored_repositories) * 100)
})
const state = computed(() => {
  const item = module.value
  if (!item || item.monitored_repositories === 0) return 'empty'
  if (item.error_repositories > 0 || coverage.value < 50) return 'error'
  if (coverage.value < 100) return 'warning'
  return 'ok'
})

const realtimeType = computed(() => ({
  actions: 'github.workflow_run',
  pull_requests: 'github.pull_request',
  issues: 'github.issues',
  releases: 'github.release'
})[props.moduleKey])

async function load(silent = false): Promise<void> {
  try { status.value = await api.get<OperationsStatus>('/operations/status') }
  catch (error) { if (!silent) toasts.error('Falha ao ler o estado da coleta', error instanceof ApiError ? error.message : undefined) }
}

async function syncNow(): Promise<void> {
  syncing.value = true
  try {
    const connections = (await api.get<GitHubConnection[]>('/github/connections')).filter((item) => item.status !== 'demo')
    if (!connections.length) { toasts.warning('Nenhuma conexão GitHub ativa'); return }
    await Promise.all(connections.map((connection) => api.post<SyncResponse>(`/github/connections/${connection.id}/sync`)))
    toasts.success('Reconciliação iniciada', 'O realtime continua ativo; a fila apenas completa/enriquece dados que o webhook não trouxe.')
    window.setTimeout(() => { void load(true); emit('refreshed') }, 2500)
  } catch (error) { toasts.error('Não foi possível iniciar a reconciliação', error instanceof ApiError ? error.message : undefined) }
  finally { syncing.value = false }
}

function handleRealtime(event: Event): void {
  const detail = (event as CustomEvent<RealtimeEvent>).detail
  if (!detail || detail.type !== realtimeType.value) return
  window.clearTimeout(realtimeTimer)
  // O backend publica somente depois do commit das tabelas operacionais.
  realtimeTimer = window.setTimeout(() => {
    void load(true)
    emit('refreshed')
  }, 80)
}

onMounted(() => {
  void load()
  window.addEventListener(REALTIME_EVENT, handleRealtime)
  // Fallback de reconciliação visual. Não é o caminho normal do monitoramento.
  timer = window.setInterval(() => { void load(true); emit('refreshed') }, 60_000)
})
onBeforeUnmount(() => {
  window.removeEventListener(REALTIME_EVENT, handleRealtime)
  window.clearTimeout(realtimeTimer)
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <section v-if="module" class="operation-status" :class="state">
    <div class="status-icon"><CheckCircle2 v-if="state==='ok'" :size="19" /><AlertTriangle v-else-if="state==='warning'" :size="19" /><ServerCrash v-else :size="19" /></div>
    <div class="status-copy">
      <strong>{{ module.label }} · coleta {{ coverage }}%</strong>
      <span v-if="module.monitored_repositories">{{ module.observed_repositories }}/{{ module.monitored_repositories }} repositórios observados · {{ module.item_count }} item(ns) coletados · última leitura {{ formatRelative(module.last_observed_at) }}</span>
      <span v-else>Nenhum repositório monitorado.</span>
      <details v-if="module.errors.length"><summary>{{ module.error_repositories }} repositório(s) com erro/permissão</summary><ul><li v-for="error in module.errors" :key="error">{{ error }}</li></ul></details>
    </div>
    <button class="button secondary compact" :disabled="syncing" @click="syncNow"><RefreshCw :size="14" :class="{spin:syncing}" />{{ syncing ? 'Reconciliando…' : 'Reconciliar agora' }}</button>
  </section>
</template>

<style scoped>
.operation-status{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.75rem .85rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface);box-shadow:var(--shadow-sm)}.status-icon{display:grid;place-items:center;width:2.35rem;height:2.35rem;border-radius:.7rem;color:var(--success);background:color-mix(in srgb,var(--success) 9%,var(--surface))}.operation-status.warning .status-icon{color:var(--warning);background:color-mix(in srgb,var(--warning) 9%,var(--surface))}.operation-status.error .status-icon,.operation-status.empty .status-icon{color:var(--danger);background:color-mix(in srgb,var(--danger) 8%,var(--surface))}.status-copy{display:grid;min-width:0}.status-copy strong{color:var(--text-strong);font-size:.72rem}.status-copy>span{color:var(--text-muted);font-size:.62rem}.status-copy details{margin-top:.25rem;color:var(--danger);font-size:.58rem}.status-copy summary{cursor:pointer}.status-copy ul{max-height:120px;overflow:auto;margin:.3rem 0 0;padding-left:1rem;color:var(--text-muted)}
@media(max-width:650px){.operation-status{grid-template-columns:auto 1fr}.operation-status>.button{grid-column:1/-1;width:100%}}
</style>
