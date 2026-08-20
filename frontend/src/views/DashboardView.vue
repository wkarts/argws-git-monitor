<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Component } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Github,
  Globe2,
  Layers3,
  LockKeyhole,
  RefreshCw,
  Rocket,
  Search,
  Settings,
  Timer,
  XCircle
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import HealthDonut from '../components/HealthDonut.vue'
import OverviewMetricCard from '../components/OverviewMetricCard.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import { useToastStore } from '../stores/toast'
import type {
  DashboardData,
  DashboardWorkflow,
  GitHubConnection,
  NotificationItem,
  Repository,
  SyncResponse
} from '../types/api'

interface ActivityItem {
  id: string
  title: string
  subtitle: string
  date: string | null
  tone: 'success' | 'warning' | 'danger' | 'info'
  icon: Component
  to: string
}

const toasts = useToastStore()
const data = ref<DashboardData | null>(null)
const connections = ref<GitHubConnection[]>([])
const loading = ref(true)
const syncing = ref(false)
const errorMessage = ref('')
const repositorySearch = ref('')
let refreshTimer: ReturnType<typeof setInterval> | null = null

const hasDemo = computed(() => connections.value.some((item) => item.status === 'demo'))
const realConnections = computed(() => connections.value.filter((item) => item.status !== 'demo'))
const criticalCount = computed(() => (data.value?.stats.failing || 0) + (data.value?.stats.attention || 0))
const criticalRepository = computed(() =>
  data.value?.repositories.find((repository) => repository.health_status === 'failing')
  || data.value?.repositories.find((repository) => repository.health_status === 'attention')
  || null
)

const filteredRepositories = computed(() => {
  const repositories = data.value?.repositories || []
  const query = repositorySearch.value.trim().toLocaleLowerCase('pt-BR')
  if (!query) return repositories
  return repositories.filter((repository) =>
    [repository.full_name, repository.description, repository.language, repository.default_branch]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase('pt-BR').includes(query))
  )
})

const healthRows = computed(() => {
  if (!data.value) return []
  const total = Math.max(data.value.stats.total_repositories, 1)
  const rows = [
    { label: 'OK', count: data.value.stats.healthy, tone: 'success' },
    { label: 'Executando', count: data.value.stats.running, tone: 'warning' },
    { label: 'Falhou / atenção', count: criticalCount.value, tone: 'danger' },
    { label: 'Desconectado', count: data.value.stats.unknown, tone: 'neutral' }
  ]
  return rows.map((row) => ({ ...row, percent: Math.round((row.count / total) * 100) }))
})

const mobileHealthRingStyle = computed(() => {
  if (!data.value) return {}
  const total = Math.max(data.value.stats.total_repositories, 1)
  const healthyEnd = (data.value.stats.healthy / total) * 360
  const runningEnd = healthyEnd + (data.value.stats.running / total) * 360
  const criticalEnd = runningEnd + (criticalCount.value / total) * 360
  return {
    background: `conic-gradient(
      var(--success) 0deg ${healthyEnd}deg,
      var(--warning) ${healthyEnd}deg ${runningEnd}deg,
      var(--danger) ${runningEnd}deg ${criticalEnd}deg,
      var(--text-subtle) ${criticalEnd}deg 360deg
    )`
  }
})

function workflowTone(run: DashboardWorkflow): ActivityItem['tone'] {
  const value = (run.conclusion || run.status || '').toLowerCase()
  if (['failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'].includes(value)) return 'danger'
  if (['queued', 'in_progress', 'waiting', 'pending'].includes(value)) return 'warning'
  if (value === 'success') return 'success'
  return 'info'
}

function workflowTitle(run: DashboardWorkflow): string {
  const value = (run.conclusion || run.status || '').toLowerCase()
  if (['failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'].includes(value)) return `${run.name} falhou`
  if (['queued', 'in_progress', 'waiting', 'pending'].includes(value)) return `${run.name} em execução`
  if (value === 'success') return `${run.name} concluída`
  return run.name
}

function notificationTone(item: NotificationItem): ActivityItem['tone'] {
  if (item.severity === 'error') return 'danger'
  if (item.severity === 'warning') return 'warning'
  if (item.severity === 'success') return 'success'
  return 'info'
}

const recentActivities = computed<ActivityItem[]>(() => {
  if (!data.value) return []
  const workflows: ActivityItem[] = data.value.recent_workflows.map((run) => ({
    id: `workflow-${run.id}`,
    title: workflowTitle(run),
    subtitle: run.repository_full_name,
    date: run.github_updated_at || run.github_created_at,
    tone: workflowTone(run),
    icon: workflowTone(run) === 'danger' ? XCircle : workflowTone(run) === 'success' ? CheckCircle2 : Timer,
    to: `/repositories/${run.repository_id}`
  }))
  const notifications: ActivityItem[] = data.value.recent_notifications.map((item) => ({
    id: `notification-${item.id}`,
    title: item.title,
    subtitle: item.message,
    date: item.created_at,
    tone: notificationTone(item),
    icon: notificationTone(item) === 'danger' ? XCircle : notificationTone(item) === 'success' ? CheckCircle2 : CircleDot,
    to: item.repository_id ? `/repositories/${item.repository_id}` : '/notifications'
  }))
  return [...workflows, ...notifications]
    .sort((left, right) => new Date(right.date || 0).getTime() - new Date(left.date || 0).getTime())
    .slice(0, 5)
})

function workflowStatus(repository: Repository): string {
  return repository.latest_workflow_conclusion || repository.latest_workflow_status || 'unknown'
}

async function load(silent = false): Promise<void> {
  if (!silent) {
    loading.value = true
    errorMessage.value = ''
  }
  try {
    const [dashboard, connectionList] = await Promise.all([
      api.get<DashboardData>('/dashboard'),
      api.get<GitHubConnection[]>('/github/connections')
    ])
    data.value = dashboard
    connections.value = connectionList
  } catch (error) {
    if (!silent) errorMessage.value = error instanceof ApiError ? error.message : 'Falha ao carregar o dashboard.'
  } finally {
    if (!silent) loading.value = false
  }
}

async function syncAll(): Promise<void> {
  if (!realConnections.value.length) {
    toasts.info('Conecte o GitHub', 'Adicione uma conexão real antes de sincronizar.')
    return
  }
  syncing.value = true
  try {
    await Promise.all(
      realConnections.value.map((connection) => api.post<SyncResponse>(`/github/connections/${connection.id}/sync`))
    )
    toasts.success('Sincronização iniciada', 'Os workers atualizarão todos os repositórios monitorados.')
    window.setTimeout(() => void load(true), 5000)
  } catch (error) {
    toasts.error('Não foi possível sincronizar', error instanceof ApiError ? error.message : undefined)
  } finally {
    syncing.value = false
  }
}

onMounted(() => {
  void load()
  refreshTimer = window.setInterval(() => void load(true), 60_000)
})

onBeforeUnmount(() => {
  if (refreshTimer !== null) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="dashboard-page">
    <section class="dashboard-toolbar">
      <div>
        <span>MONITORAMENTO EM TEMPO REAL</span>
        <h2>Visão geral dos repositórios</h2>
        <p>Saúde, CI/CD, pull requests, releases e alertas em um único painel.</p>
      </div>
      <button class="button secondary" :disabled="syncing" @click="syncAll">
        <RefreshCw :size="16" :class="{ spin: syncing }" />
        {{ syncing ? 'Sincronizando…' : 'Sincronizar tudo' }}
      </button>
    </section>

    <section v-if="hasDemo" class="demo-banner">
      <div class="demo-icon"><Rocket :size="21" /></div>
      <div><strong>Modo de demonstração ativo</strong><span>Conecte o GitHub para substituir os exemplos pelos seus repositórios reais.</span></div>
      <RouterLink to="/settings" class="button primary compact"><Settings :size="15" />Conectar GitHub</RouterLink>
    </section>

    <div v-if="loading" class="dashboard-loading">
      <div v-for="index in 4" :key="`metric-${index}`" class="skeleton metric-skeleton" />
      <div class="skeleton overview-skeleton" />
      <div class="skeleton overview-skeleton" />
      <div class="skeleton table-skeleton" />
    </div>

    <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Não foi possível carregar o monitor" :message="errorMessage">
      <button class="button secondary compact" @click="load"><RefreshCw :size="15" />Tentar novamente</button>
    </EmptyState>

    <template v-else-if="data">
      <section class="overview-metrics">
        <OverviewMetricCard :value="data.stats.total_repositories" label="repositórios" helper="monitorados" :icon="Layers3" tone="primary" />
        <OverviewMetricCard :value="data.stats.healthy" label="OK" helper="funcionando bem" :icon="CheckCircle2" tone="success" />
        <OverviewMetricCard :value="data.stats.running" label="executando" helper="em andamento" :icon="Timer" tone="warning" />
        <OverviewMetricCard :value="data.stats.failing" label="falhou" helper="precisa de atenção" :icon="XCircle" tone="danger" />
      </section>

      <article class="mobile-health-summary">
        <div class="mobile-health-summary-top">
          <div class="mobile-health-score">
            <span>Saúde geral</span>
            <strong>{{ Math.round(data.stats.average_health_score) }}%</strong>
            <small>saúde geral</small>
          </div>
          <div class="mobile-health-ring" :style="mobileHealthRingStyle"><i /></div>
        </div>
        <div class="mobile-health-summary-rows">
          <div v-for="row in healthRows.slice(0, 3)" :key="`mobile-${row.label}`" class="mobile-health-summary-row" :class="`tone-${row.tone}`">
            <div><i /><span>{{ row.count }} {{ row.label }}</span></div>
            <div class="mobile-health-summary-progress"><span :style="{ width: `${row.percent}%` }" /></div>
            <strong>{{ row.percent }}%</strong>
          </div>
        </div>
      </article>

      <section class="dashboard-overview-grid">
        <article class="monitor-panel health-overview-panel">
          <header><div><h3>Saúde geral dos repositórios</h3><span>Índice consolidado da operação</span></div><CircleDot :size="16" /></header>
          <div class="health-overview-content">
            <HealthDonut
              :score="data.stats.average_health_score"
              :healthy="data.stats.healthy"
              :running="data.stats.running"
              :critical="criticalCount"
              :unknown="data.stats.unknown"
              :size="168"
            />
            <div class="health-status-list">
              <div v-for="row in healthRows" :key="row.label" class="health-status-row" :class="`tone-${row.tone}`">
                <div><i /><span>{{ row.label }}</span></div>
                <div class="health-progress"><span :style="{ width: `${row.percent}%` }" /></div>
                <strong>{{ row.percent }}%</strong>
              </div>
            </div>
          </div>
        </article>

        <article class="monitor-panel recent-activities-panel">
          <header><div><h3>Atividades recentes</h3><span>Atualizações mais importantes do GitHub</span></div><Activity :size="18" /></header>
          <div v-if="recentActivities.length" class="recent-activity-list">
            <RouterLink v-for="item in recentActivities" :key="item.id" :to="item.to" class="recent-activity-row" :class="`tone-${item.tone}`">
              <div class="activity-state"><component :is="item.icon" :size="17" /></div>
              <div class="activity-text"><strong>{{ item.title }}</strong><span>{{ item.subtitle }}</span></div>
              <small>{{ formatRelative(item.date) }}</small>
            </RouterLink>
          </div>
          <EmptyState v-else :icon="Activity" title="Sem atividades" message="As atividades aparecerão após a primeira sincronização." />
          <RouterLink to="/notifications" class="panel-link">Ver todas as atividades <ChevronRight :size="14" /></RouterLink>
        </article>
      </section>

      <section class="monitor-panel repositories-monitor-panel">
        <header class="repositories-panel-header">
          <div><h3>Repositórios monitorados</h3><span>{{ filteredRepositories.length }} projeto(s) nesta visão</span></div>
          <label class="dashboard-search"><Search :size="15" /><input v-model="repositorySearch" type="search" placeholder="Buscar repositório..." /></label>
          <RouterLink to="/repositories" class="mobile-repositories-header-link">Ver todos</RouterLink>
        </header>

        <div v-if="filteredRepositories.length" class="repository-table-wrap desktop-repository-table">
          <table class="repository-table">
            <thead><tr><th>Repositório</th><th>Status</th><th>Actions / CI</th><th>Última atividade</th><th>Branch principal</th><th aria-label="Ações" /></tr></thead>
            <tbody>
              <tr v-for="repository in filteredRepositories.slice(0, 10)" :key="repository.id">
                <td>
                  <RouterLink :to="`/repositories/${repository.id}`" class="repository-identity-link">
                    <span class="repository-privacy"><LockKeyhole v-if="repository.private" :size="14" /><Globe2 v-else :size="14" /></span>
                    <span><strong>{{ repository.name }}</strong><small>{{ repository.owner }}</small></span>
                  </RouterLink>
                </td>
                <td><StatusBadge :value="repository.health_status" health compact /></td>
                <td><StatusBadge :value="workflowStatus(repository)" compact /><small class="workflow-name">{{ repository.latest_workflow_name || 'Sem workflow' }}</small></td>
                <td>{{ formatRelative(repository.latest_workflow_at || repository.pushed_at || repository.last_synced_at) }}</td>
                <td><code>{{ repository.default_branch }}</code></td>
                <td><a :href="repository.html_url" target="_blank" rel="noopener noreferrer" class="repository-github-link" title="Abrir no GitHub"><Github :size="17" /></a><RouterLink :to="`/repositories/${repository.id}`" class="repository-github-link" title="Ver detalhes"><ChevronRight :size="17" /></RouterLink></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="filteredRepositories.length" class="mobile-repository-list">
          <RouterLink v-for="repository in filteredRepositories.slice(0, 4)" :key="repository.id" :to="`/repositories/${repository.id}`">
            <span class="repository-privacy"><LockKeyhole v-if="repository.private" :size="13" /><Globe2 v-else :size="13" /></span>
            <strong>{{ repository.name }}</strong>
            <span class="mobile-repository-state" :class="`health-${repository.health_status}`"><i />{{ repository.health_status === 'healthy' ? 'OK' : repository.health_status === 'running' ? 'Executando' : repository.health_status === 'failing' ? 'Falhou' : repository.health_status === 'attention' ? 'Atenção' : 'Sem CI' }}</span>
            <ChevronRight :size="15" />
          </RouterLink>
        </div>

        <EmptyState v-if="!filteredRepositories.length" :icon="Github" title="Nenhum repositório localizado" message="Altere o texto pesquisado ou conecte uma conta GitHub." />
        <RouterLink v-if="filteredRepositories.length" to="/repositories" class="mobile-panel-link">Ver todos os repositórios <ChevronRight :size="14" /></RouterLink>
      </section>

      <RouterLink v-if="criticalRepository" :to="`/repositories/${criticalRepository.id}`" class="mobile-critical-card">
        <div class="critical-icon"><XCircle :size="24" /></div>
        <div class="critical-copy">
          <span>FALHA DE BUILD · {{ formatRelative(criticalRepository.latest_workflow_at) }}</span>
          <strong>{{ criticalRepository.name }}</strong>
          <p>{{ criticalRepository.latest_workflow_name || 'A execução mais recente precisa de atenção.' }}</p>
          <small>Branch: {{ criticalRepository.default_branch }} · Workflow monitorado</small>
        </div>
        <ChevronRight :size="18" />
      </RouterLink>
    </template>
  </div>
</template>

<style scoped>
.dashboard-page { display: grid; gap: 0.9rem; min-width: 0; }
.dashboard-toolbar { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; margin-bottom: 0.1rem; }
.dashboard-toolbar > div { display: grid; gap: 0.14rem; }
.dashboard-toolbar span { color: var(--primary-strong); font-size: 0.58rem; font-weight: 800; letter-spacing: 0.13em; }
.dashboard-toolbar h2 { margin: 0; color: var(--text-strong); font-size: clamp(1.18rem, 2vw, 1.55rem); letter-spacing: -0.025em; }
.dashboard-toolbar p { margin: 0; color: var(--text-muted); font-size: 0.72rem; }
.demo-banner { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 0.75rem; padding: 0.72rem 0.8rem; border: 1px solid color-mix(in srgb, var(--primary) 27%, var(--border)); border-radius: 0.78rem; background: color-mix(in srgb, var(--primary) 7%, var(--surface)); }
.demo-icon { display: grid; place-items: center; width: 2.25rem; height: 2.25rem; color: var(--primary-strong); border-radius: 0.65rem; background: color-mix(in srgb, var(--primary) 12%, var(--surface)); }
.demo-banner > div:nth-child(2) { display: grid; }
.demo-banner strong { color: var(--text-strong); font-size: 0.72rem; }
.demo-banner span { color: var(--text-muted); font-size: 0.64rem; }
.overview-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
.dashboard-overview-grid { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: 0.75rem; }
.monitor-panel { min-width: 0; overflow: hidden; border: 1px solid var(--border); border-radius: 0.85rem; background: linear-gradient(145deg, var(--surface), var(--surface-raised)); box-shadow: var(--shadow-sm); }
.monitor-panel > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.8rem; padding: 0.82rem 0.9rem; border-bottom: 1px solid var(--border-soft); }
.monitor-panel > header > div { display: grid; }
.monitor-panel h3 { margin: 0; color: var(--text-strong); font-size: 0.82rem; }
.monitor-panel header span { color: var(--text-subtle); font-size: 0.59rem; }
.monitor-panel > header > svg { color: var(--text-subtle); }
.health-overview-content { display: flex; align-items: center; justify-content: center; gap: clamp(1rem, 4vw, 2.4rem); min-height: 235px; padding: 1rem; }
.health-status-list { display: grid; flex: 1; gap: 0.78rem; max-width: 310px; }
.health-status-row { display: grid; grid-template-columns: minmax(90px, 1fr) minmax(70px, 1.25fr) auto; align-items: center; gap: 0.65rem; --row-color: var(--text-subtle); }
.health-status-row > div:first-child { display: flex; align-items: center; gap: 0.45rem; }
.health-status-row i { width: 0.48rem; height: 0.48rem; border-radius: 50%; background: var(--row-color); box-shadow: 0 0 0 3px color-mix(in srgb, var(--row-color) 12%, transparent); }
.health-status-row span,.health-status-row strong { font-size: 0.65rem; }
.health-status-row > div:first-child span { color: var(--text-muted); }
.health-status-row strong { min-width: 2.3rem; color: var(--text); text-align: right; }
.health-progress { height: 0.28rem; overflow: hidden; border-radius: 999px; background: var(--surface-soft); }
.health-progress > span { display: block; height: 100%; border-radius: inherit; background: var(--row-color); }
.health-status-row.tone-success { --row-color: var(--success); }
.health-status-row.tone-warning { --row-color: var(--warning); }
.health-status-row.tone-danger { --row-color: var(--danger); }
.recent-activities-panel { display: flex; flex-direction: column; }
.recent-activity-list { display: grid; padding: 0 0.9rem; }
.recent-activity-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.68rem; min-height: 3.3rem; color: inherit; text-decoration: none; border-bottom: 1px solid var(--border-soft); --activity-color: var(--info); }
.recent-activity-row:last-child { border-bottom: 0; }
.activity-state { display: grid; place-items: center; width: 1.8rem; height: 1.8rem; color: white; border-radius: 50%; background: var(--activity-color); box-shadow: 0 0 0 5px color-mix(in srgb, var(--activity-color) 7%, transparent); }
.activity-text { display: grid; min-width: 0; }
.activity-text strong,.activity-text span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.activity-text strong { color: var(--text); font-size: 0.69rem; }
.activity-text span { color: var(--text-subtle); font-size: 0.59rem; }
.recent-activity-row small { color: var(--text-subtle); font-size: 0.57rem; white-space: nowrap; }
.recent-activity-row.tone-success { --activity-color: var(--success); }
.recent-activity-row.tone-warning { --activity-color: var(--warning); }
.recent-activity-row.tone-danger { --activity-color: var(--danger); }
.panel-link,.mobile-panel-link { display: inline-flex; align-items: center; justify-content: flex-end; gap: 0.25rem; margin: auto 0.9rem 0.7rem; color: var(--primary-strong); font-size: 0.61rem; text-decoration: none; }
.repositories-panel-header { align-items: center !important; }
.dashboard-search { position: relative; display: flex; align-items: center; width: min(300px, 100%); }
.dashboard-search svg { position: absolute; left: 0.65rem; color: var(--text-subtle); }
.dashboard-search input { width: 100%; min-height: 2.15rem; padding: 0.42rem 0.7rem 0.42rem 2rem; color: var(--text); border: 1px solid var(--border); border-radius: 0.58rem; outline: none; background: var(--surface-soft); font-size: 0.66rem; }
.dashboard-search input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 11%, transparent); }
.repository-table-wrap { overflow-x: auto; }
.repository-table { width: 100%; border-collapse: collapse; }
.repository-table th { padding: 0.62rem 0.78rem; color: var(--text-subtle); text-align: left; font-size: 0.56rem; font-weight: 720; white-space: nowrap; background: color-mix(in srgb, var(--surface-soft) 78%, transparent); }
.repository-table td { min-width: 105px; padding: 0.62rem 0.78rem; color: var(--text-muted); font-size: 0.63rem; border-top: 1px solid var(--border-soft); }
.repository-table tbody tr { transition: background 0.14s ease; }
.repository-table tbody tr:hover { background: color-mix(in srgb, var(--primary) 4%, transparent); }
.repository-table td:nth-child(1) { min-width: 210px; }
.repository-table td:nth-child(3) { min-width: 190px; }
.repository-table td:last-child { display: flex; align-items: center; justify-content: flex-end; gap: 0.18rem; min-width: 70px; }
.repository-identity-link { display: flex; align-items: center; gap: 0.55rem; color: inherit; text-decoration: none; }
.repository-identity-link > span:last-child { display: grid; min-width: 0; }
.repository-identity-link strong,.repository-identity-link small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.repository-identity-link strong { color: var(--text); font-size: 0.67rem; }
.repository-identity-link small { color: var(--text-subtle); font-size: 0.56rem; }
.repository-privacy { display: grid; place-items: center; flex: 0 0 auto; color: var(--text-muted); }
.workflow-name { display: block; max-width: 170px; margin-top: 0.18rem; overflow: hidden; color: var(--text-subtle); font-size: 0.54rem; text-overflow: ellipsis; white-space: nowrap; }
.repository-table code { padding: 0.18rem 0.42rem; color: var(--primary-strong); border-radius: 0.38rem; background: color-mix(in srgb, var(--primary) 8%, var(--surface)); font-size: 0.58rem; }
.repository-github-link { display: grid; place-items: center; width: 1.8rem; height: 1.8rem; color: var(--text-muted); border-radius: 0.45rem; text-decoration: none; }
.repository-github-link:hover { color: var(--primary-strong); background: var(--surface-soft); }
.mobile-health-summary,.mobile-repository-list,.mobile-panel-link,.mobile-critical-card,.mobile-repositories-header-link { display: none; }
.dashboard-loading { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
.metric-skeleton { height: 104px; border-radius: 0.9rem; }
.overview-skeleton { grid-column: span 2; height: 290px; border-radius: 0.85rem; }
.table-skeleton { grid-column: 1 / -1; height: 320px; border-radius: 0.85rem; }

@media (max-width: 1180px) {
  .overview-metrics { grid-template-columns: repeat(2, 1fr); }
  .dashboard-overview-grid { grid-template-columns: 1fr; }
}

@media (max-width: 899px) {
  .dashboard-toolbar { display: none; }
  .demo-banner,.overview-metrics,.dashboard-overview-grid { display: none; }
  .mobile-health-summary {
    display: grid;
    gap: 0.7rem;
    padding: 0.9rem;
    border: 1px solid var(--border);
    border-radius: 0.78rem;
    background: linear-gradient(145deg, var(--surface), var(--surface-raised));
    box-shadow: var(--shadow-sm);
  }
  .mobile-health-summary-top { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; }
  .mobile-health-score { display: grid; }
  .mobile-health-score span { color: var(--text-muted); font-size: 0.61rem; }
  .mobile-health-score strong { margin-top: 0.14rem; color: var(--text-strong); font-size: 1.8rem; line-height: 1; letter-spacing: -0.04em; }
  .mobile-health-score small { margin-top: 0.3rem; color: var(--text-subtle); font-size: 0.55rem; }
  .mobile-health-ring { position: relative; display: grid; place-items: center; width: 5.7rem; height: 5.7rem; flex: 0 0 auto; border-radius: 50%; }
  .mobile-health-ring i { width: 4.15rem; height: 4.15rem; border: 1px solid var(--border); border-radius: 50%; background: var(--surface); }
  .mobile-health-summary-rows { display: grid; gap: 0.48rem; }
  .mobile-health-summary-row { display: grid; grid-template-columns: minmax(85px, 1fr) minmax(75px, 1.5fr) auto; align-items: center; gap: 0.45rem; --row-color: var(--text-subtle); }
  .mobile-health-summary-row > div:first-child { display: flex; align-items: center; gap: 0.38rem; min-width: 0; }
  .mobile-health-summary-row i { width: 0.4rem; height: 0.4rem; flex: 0 0 auto; border-radius: 50%; background: var(--row-color); }
  .mobile-health-summary-row span,.mobile-health-summary-row strong { color: var(--text-muted); font-size: 0.55rem; }
  .mobile-health-summary-row strong { min-width: 1.75rem; text-align: right; }
  .mobile-health-summary-progress { height: 0.24rem; overflow: hidden; border-radius: 999px; background: var(--surface-soft); }
  .mobile-health-summary-progress > span { display: block; height: 100%; border-radius: inherit; background: var(--row-color); }
  .mobile-health-summary-row.tone-success { --row-color: var(--success); }
  .mobile-health-summary-row.tone-warning { --row-color: var(--warning); }
  .mobile-health-summary-row.tone-danger { --row-color: var(--danger); }
  .monitor-panel { border-radius: 0.78rem; }
  .desktop-repository-table { display: none; }
  .repositories-panel-header { align-items: center !important; padding: 0.72rem !important; }
  .repositories-panel-header > div span,.dashboard-search { display: none; }
  .mobile-repositories-header-link { display: inline-flex; margin-left: auto; color: var(--primary-strong); font-size: 0.59rem; text-decoration: none; }
  .mobile-repository-list { display: grid; padding: 0 0.72rem; }
  .mobile-repository-list a { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 0.5rem; min-height: 2.75rem; color: inherit; text-decoration: none; border-bottom: 1px solid var(--border-soft); }
  .mobile-repository-list a:last-child { border-bottom: 0; }
  .mobile-repository-list strong { overflow: hidden; color: var(--text); font-size: 0.65rem; text-overflow: ellipsis; white-space: nowrap; }
  .mobile-repository-state { display: inline-flex; align-items: center; gap: 0.32rem; color: var(--text-muted); font-size: 0.56rem; white-space: nowrap; }
  .mobile-repository-state i { width: 0.42rem; height: 0.42rem; border-radius: 50%; background: currentColor; }
  .health-healthy { color: var(--success); }
  .health-running { color: var(--warning); }
  .health-failing { color: var(--danger); }
  .health-attention { color: var(--warning); }
  .mobile-panel-link { display: none; }
  .mobile-critical-card { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 0.68rem; padding: 0.85rem; color: inherit; text-decoration: none; border: 1px solid color-mix(in srgb, var(--danger) 40%, var(--border)); border-radius: 0.78rem; background: linear-gradient(145deg, color-mix(in srgb, var(--danger) 13%, var(--surface)), color-mix(in srgb, var(--danger) 5%, var(--surface-raised))); box-shadow: 0 12px 30px color-mix(in srgb, var(--danger) 9%, transparent); }
  .critical-icon { display: grid; place-items: center; width: 2.65rem; height: 2.65rem; color: white; border-radius: 50%; background: var(--danger); box-shadow: 0 0 0 6px color-mix(in srgb, var(--danger) 10%, transparent); }
  .critical-copy { display: grid; min-width: 0; }
  .critical-copy > span { color: color-mix(in srgb, var(--danger) 75%, #fff); font-size: 0.52rem; font-weight: 850; letter-spacing: 0.08em; }
  .critical-copy strong { margin-top: 0.1rem; color: var(--text-strong); font-size: 0.76rem; }
  .critical-copy p { margin: 0.05rem 0; overflow: hidden; color: var(--text-muted); font-size: 0.6rem; text-overflow: ellipsis; white-space: nowrap; }
  .critical-copy small { color: var(--text-subtle); font-size: 0.52rem; }
  .dashboard-loading { grid-template-columns: 1fr; }
  .metric-skeleton { display: none; }
  .overview-skeleton,.table-skeleton { grid-column: 1; }
  .dashboard-loading .overview-skeleton:nth-of-type(6) { display: none; }
}

@media (max-width: 590px) {
  .health-overview-content { flex-direction: column; min-height: 0; padding: 0.95rem; }
  .health-status-list { width: 100%; max-width: none; }
  .recent-activity-row { grid-template-columns: auto minmax(0, 1fr); padding: 0.2rem 0; }
  .recent-activity-row > small { grid-column: 2; }
}

@media (max-width: 430px) {
  .overview-metrics { gap: 0.48rem; }
  .demo-banner { display: none; }
  .monitor-panel > header { padding: 0.72rem; }
  .recent-activity-list { padding-inline: 0.72rem; }
}
</style>
