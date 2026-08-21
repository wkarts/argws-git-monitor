<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, Clock3, ListChecks, RefreshCw, RotateCcw, XCircle } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { formatDateTime } from '../services/format'
import { useToastStore } from '../stores/toast'
import type { MessageResponse, QueueOverview, SyncJob, SyncJobStatus } from '../types/api'

const toasts = useToastStore()
const jobs = ref<SyncJob[]>([])
const overview = ref<QueueOverview>({ queued: 0, running: 0, succeeded: 0, failed: 0, total: 0 })
const statusFilter = ref<SyncJobStatus | ''>('')
const loading = ref(true)
const errorMessage = ref('')
let timer: number | undefined

const activeCount = computed(() => overview.value.queued + overview.value.running)
const cards = computed(() => [
  { label: 'Na fila', value: overview.value.queued, icon: Clock3, tone: 'warning' },
  { label: 'Executando', value: overview.value.running, icon: RotateCcw, tone: 'info' },
  { label: 'Concluídos', value: overview.value.succeeded, icon: CheckCircle2, tone: 'success' },
  { label: 'Falharam', value: overview.value.failed, icon: AlertCircle, tone: 'danger' }
])

function progress(job: SyncJob): number {
  if (job.status === 'success') return 100
  if (!job.progress_total) return job.status === 'running' ? 48 : 0
  return Math.min(100, Math.round((job.progress_current / job.progress_total) * 100))
}

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  errorMessage.value = ''
  try {
    const suffix = statusFilter.value ? `?status=${statusFilter.value}` : ''
    const [summary, items] = await Promise.all([
      api.get<QueueOverview>('/jobs/overview'),
      api.get<SyncJob[]>(`/jobs${suffix}`)
    ])
    overview.value = summary
    jobs.value = items
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível consultar a fila.'
  } finally {
    loading.value = false
  }
}

async function cancel(job: SyncJob): Promise<void> {
  if (!window.confirm(`Cancelar “${job.label}”?`)) return
  try {
    const response = await api.post<MessageResponse>(`/jobs/${job.id}/cancel`)
    toasts.success('Cancelamento solicitado', response.message)
    await load(true)
  } catch (error) {
    toasts.error('Não foi possível cancelar', error instanceof ApiError ? error.message : undefined)
  }
}

function statusLabel(status: SyncJobStatus): string {
  return ({ queued: 'Na fila', running: 'Executando', success: 'Concluído', failed: 'Falhou', cancelled: 'Cancelado' })[status]
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => void load(true), 4000)
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div class="page-stack queue-page">
    <section class="page-heading">
      <div><span class="eyebrow">PROCESSAMENTO ASSÍNCRONO</span><h2>Fila operacional</h2><p>Acompanhe em tempo real importações, sincronizações e processamento dos repositórios.</p></div>
      <button class="button secondary" @click="load()"><RefreshCw :size="16" />Atualizar</button>
    </section>

    <section class="queue-metrics">
      <article v-for="card in cards" :key="card.label" class="queue-metric" :class="card.tone">
        <div><component :is="card.icon" :size="20" /></div><span><strong>{{ card.value }}</strong><small>{{ card.label }}</small></span>
      </article>
    </section>

    <section class="queue-toolbar">
      <div class="live-state"><i :class="{ active: activeCount > 0 }" /><strong>{{ activeCount ? `${activeCount} processamento(s) ativo(s)` : 'Fila em repouso' }}</strong></div>
      <select v-model="statusFilter" @change="load()">
        <option value="">Todos os estados</option><option value="queued">Na fila</option><option value="running">Executando</option><option value="success">Concluídos</option><option value="failed">Falharam</option><option value="cancelled">Cancelados</option>
      </select>
    </section>

    <section class="queue-panel">
      <div v-if="loading" class="queue-loading"><span v-for="n in 5" :key="n" class="skeleton" /></div>
      <div v-else-if="errorMessage" class="queue-empty"><AlertCircle :size="28" /><strong>Falha ao carregar a fila</strong><p>{{ errorMessage }}</p><button class="button secondary" @click="load()">Tentar novamente</button></div>
      <div v-else-if="!jobs.length" class="queue-empty"><ListChecks :size="30" /><strong>Nenhum processamento registrado</strong><p>Ao monitorar ou sincronizar repositórios, os jobs aparecerão aqui com o estado real.</p></div>
      <article v-for="job in jobs" v-else :key="job.id" class="job-row">
        <div class="job-state" :class="job.status"><RotateCcw v-if="job.status === 'running'" :size="18" class="spin" /><Clock3 v-else-if="job.status === 'queued'" :size="18" /><CheckCircle2 v-else-if="job.status === 'success'" :size="18" /><XCircle v-else :size="18" /></div>
        <div class="job-main">
          <div class="job-title"><strong>{{ job.label }}</strong><span :class="`job-badge ${job.status}`">{{ statusLabel(job.status) }}</span></div>
          <p>{{ job.error || job.message || 'Sem detalhes adicionais.' }}</p>
          <div v-if="job.status === 'running' || job.progress_total" class="progress-track"><span :style="{ width: `${progress(job)}%` }" /></div>
          <div class="job-meta"><span>{{ job.kind }}</span><span>Criado {{ formatDateTime(job.created_at) }}</span><span v-if="job.completed_at">Finalizado {{ formatDateTime(job.completed_at) }}</span></div>
        </div>
        <button v-if="job.status === 'queued' || job.status === 'running'" class="button ghost compact danger-text" @click="cancel(job)">Cancelar</button>
      </article>
    </section>
  </div>
</template>

<style scoped>
.queue-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem}.queue-metric{display:flex;align-items:center;gap:.8rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.queue-metric>div{display:grid;place-items:center;width:2.65rem;height:2.65rem;border-radius:.8rem;background:var(--surface-soft);color:var(--primary-strong)}.queue-metric span{display:grid}.queue-metric strong{color:var(--text-strong);font-size:1.35rem}.queue-metric small{color:var(--text-muted);font-weight:700}.queue-metric.success>div{color:var(--success);background:color-mix(in srgb,var(--success) 10%,var(--surface))}.queue-metric.warning>div{color:var(--warning)}.queue-metric.danger>div{color:var(--danger)}
.queue-toolbar{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.7rem .85rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface)}.live-state{display:flex;align-items:center;gap:.5rem;color:var(--text-muted);font-size:.74rem}.live-state i{width:.55rem;height:.55rem;border-radius:50%;background:var(--text-subtle)}.live-state i.active{background:var(--success);box-shadow:0 0 0 5px color-mix(in srgb,var(--success) 12%,transparent)}.queue-toolbar select{min-height:2.25rem;color:var(--text);border:1px solid var(--border);border-radius:.65rem;background:var(--surface-soft);padding:0 .7rem}
.queue-panel{overflow:hidden;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.job-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:.85rem;padding:1rem;border-bottom:1px solid var(--border-soft)}.job-row:last-child{border-bottom:0}.job-state{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:.75rem;color:var(--text-muted);background:var(--surface-soft)}.job-state.running{color:var(--primary-strong)}.job-state.success{color:var(--success)}.job-state.failed{color:var(--danger)}.job-main{display:grid;gap:.38rem;min-width:0}.job-title{display:flex;align-items:center;gap:.55rem;min-width:0}.job-title strong{overflow:hidden;color:var(--text-strong);font-size:.82rem;text-overflow:ellipsis;white-space:nowrap}.job-badge{padding:.18rem .42rem;border-radius:999px;color:var(--text-muted);background:var(--surface-soft);font-size:.6rem;font-weight:800}.job-badge.running{color:var(--primary-strong)}.job-badge.success{color:var(--success)}.job-badge.failed{color:var(--danger)}.job-main p{margin:0;color:var(--text-muted);font-size:.72rem}.job-meta{display:flex;flex-wrap:wrap;gap:.75rem;color:var(--text-subtle);font-size:.62rem}.progress-track{height:.32rem;overflow:hidden;border-radius:999px;background:var(--surface-soft)}.progress-track span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--primary),var(--secondary));transition:width .3s ease}.queue-loading{display:grid;gap:1px}.queue-loading span{height:72px}.queue-empty{display:grid;place-items:center;gap:.5rem;padding:4rem 1rem;color:var(--text-muted);text-align:center}.queue-empty strong{color:var(--text-strong)}.queue-empty p{max-width:560px;margin:0;font-size:.75rem}
@media(max-width:900px){.queue-metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.queue-metrics{grid-template-columns:1fr 1fr}.queue-toolbar{align-items:stretch;flex-direction:column}.queue-toolbar select{width:100%}.job-row{grid-template-columns:auto 1fr}.job-row>.button{grid-column:1/-1;width:100%}.job-meta{display:grid;gap:.2rem}}
</style>
