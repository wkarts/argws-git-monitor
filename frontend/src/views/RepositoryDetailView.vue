<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  AlertTriangle, ArrowLeft, Ban, Box, CheckCircle2, Clock3, Code2, ExternalLink,
  GitBranch, GitCommitHorizontal, Github, GitPullRequest, Globe2, LockKeyhole,
  Play, RefreshCw, RotateCcw, Tag, UserRound, XCircle
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import HealthRing from '../components/HealthRing.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../services/api'
import { formatDateTime, formatDuration, formatRelative, shortSha } from '../services/format'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { RepositoryDetail, Repository, SyncResponse, WorkflowActionResponse, WorkflowRun } from '../types/api'

type TabName = 'actions' | 'pulls' | 'releases'

const route = useRoute()
const dialogs = useDialogStore()
const toasts = useToastStore()
const repository = ref<RepositoryDetail | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const activeTab = ref<TabName>('actions')
const syncing = ref(false)
const actionRunId = ref<number | null>(null)
const repositoryId = computed(() => String(route.params.id))

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try { repository.value = await api.get<RepositoryDetail>(`/repositories/${repositoryId.value}`) }
  catch (error) { errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível abrir o repositório.' }
  finally { loading.value = false }
}

async function syncNow(): Promise<void> {
  if (!repository.value) return
  syncing.value = true
  try {
    const result = await api.post<SyncResponse>(`/repositories/${repository.value.id}/sync`)
    toasts.success('Sincronização agendada', result.message)
  } catch (error) { toasts.error('Falha ao sincronizar', error instanceof ApiError ? error.message : undefined) }
  finally { syncing.value = false }
}

async function toggleMonitoring(): Promise<void> {
  if (!repository.value) return
  const nextValue = !repository.value.monitoring_enabled
  const accepted = await dialogs.askConfirmation({
    title: nextValue ? 'Ativar monitoramento?' : 'Pausar monitoramento?',
    message: `${repository.value.full_name} ${nextValue ? 'voltará a receber reconciliação e eventos do monitor.' : 'deixará de ser reconciliado enquanto estiver pausado.'}`,
    tone: nextValue ? 'info' : 'warning',
    confirmLabel: nextValue ? 'Ativar monitoramento' : 'Pausar monitoramento',
  })
  if (!accepted) return
  try {
    const updated = await api.patch<Repository>(`/repositories/${repository.value.id}`, { monitoring_enabled: nextValue })
    repository.value.monitoring_enabled = updated.monitoring_enabled
    toasts.success(nextValue ? 'Monitoramento ativado' : 'Monitoramento pausado')
  } catch (error) { toasts.error('Não foi possível alterar', error instanceof ApiError ? error.message : undefined) }
}

async function workflowAction(run: WorkflowRun, action: 'rerun' | 'rerun-failed' | 'cancel'): Promise<void> {
  if (!repository.value) return
  const labels = { rerun: 'reexecutar todo o workflow', 'rerun-failed': 'reexecutar somente os jobs com falha', cancel: 'cancelar esta execução' }
  const accepted = await dialogs.askConfirmation({
    title: action === 'cancel' ? 'Cancelar execução do GitHub Actions?' : 'Reexecutar GitHub Actions?',
    message: `${run.name} · execução #${run.run_number || run.github_id}\n\nA ação solicitada é: ${labels[action]}.`,
    tone: action === 'cancel' ? 'warning' : 'info',
    confirmLabel: action === 'cancel' ? 'Cancelar execução' : 'Reexecutar',
  })
  if (!accepted) return
  actionRunId.value = run.github_id
  try {
    const result = await api.post<WorkflowActionResponse>(`/repositories/${repository.value.id}/workflow-runs/${run.github_id}/${action}`)
    toasts.success('Ação enviada ao GitHub', result.message)
    window.setTimeout(() => void load(), 2500)
  } catch (error) { toasts.error('GitHub recusou a ação', error instanceof ApiError ? error.message : undefined) }
  finally { actionRunId.value = null }
}

onMounted(load)
watch(repositoryId, load)
</script>

<template>
  <div class="page-stack">
    <RouterLink to="/repositories" class="back-link"><ArrowLeft :size="16" />Voltar aos repositórios</RouterLink>
    <div v-if="loading" class="detail-loading"><div class="skeleton hero-skeleton" /><div class="skeleton content-skeleton" /></div>
    <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Repositório indisponível" :message="errorMessage"><button class="button secondary small" @click="load"><RefreshCw :size="15" />Tentar novamente</button></EmptyState>
    <template v-else-if="repository">
      <section class="repository-hero">
        <div class="repo-title-wrap"><div class="repo-large-icon"><Code2 :size="28" /></div><div class="repo-title"><div class="repo-path"><span>{{ repository.owner }}</span><strong>/</strong><span>{{ repository.name }}</span></div><h2>{{ repository.full_name }}</h2><p>{{ repository.description || 'Sem descrição cadastrada no GitHub.' }}</p><div class="hero-badges"><StatusBadge :value="repository.health_status" health /><span><LockKeyhole v-if="repository.private" :size="14" /><Globe2 v-else :size="14" />{{ repository.private ? 'Privado' : 'Público' }}</span><span><GitBranch :size="14" />{{ repository.default_branch }}</span><span v-if="repository.language"><Code2 :size="14" />{{ repository.language }}</span></div></div></div>
        <div class="hero-actions"><HealthRing :score="repository.health_score" :size="86" /><div class="button-row"><button class="button secondary small" :disabled="syncing || !repository.monitoring_enabled" @click="syncNow"><RefreshCw :size="15" :class="{ spin: syncing }" />Sincronizar</button><a class="button ghost small" :href="repository.html_url" target="_blank" rel="noopener noreferrer"><Github :size="15" />GitHub<ExternalLink :size="13" /></a><button class="button ghost small" @click="toggleMonitoring"><Ban :size="15" />{{ repository.monitoring_enabled ? 'Pausar' : 'Ativar' }}</button></div></div>
      </section>
      <section v-if="repository.sync_error" class="error-banner"><XCircle :size="18" /><div><strong>Última sincronização com erro</strong><p>{{ repository.sync_error }}</p></div></section>
      <section class="detail-stats"><article><GitCommitHorizontal :size="19" /><span><small>Último commit</small><strong>{{ shortSha(repository.latest_commit_sha) }}</strong><em>{{ formatRelative(repository.latest_commit_at) }}</em></span></article><article><GitPullRequest :size="19" /><span><small>Pull requests</small><strong>{{ repository.open_pr_count }}</strong><em>abertas</em></span></article><article><AlertTriangle :size="19" /><span><small>Issues</small><strong>{{ repository.open_issue_count }}</strong><em>abertas</em></span></article><article><Tag :size="19" /><span><small>Última release</small><strong>{{ repository.latest_release_tag || '—' }}</strong><em>{{ formatRelative(repository.latest_release_at) }}</em></span></article><article><GitBranch :size="19" /><span><small>Branches</small><strong>{{ repository.branch_count }}</strong><em>localizadas</em></span></article></section>
      <section class="detail-grid">
        <article class="panel commit-panel"><header><GitCommitHorizontal :size="18" /><div><span>COMMIT MAIS RECENTE</span><h3>{{ shortSha(repository.latest_commit_sha) }}</h3></div></header><p>{{ repository.latest_commit_message || 'Nenhum commit retornado.' }}</p><footer><span><UserRound :size="14" />{{ repository.latest_commit_author || 'Autor desconhecido' }}</span><span><Clock3 :size="14" />{{ formatDateTime(repository.latest_commit_at) }}</span></footer></article>
        <article class="panel workflow-panel"><header><StatusBadge :value="repository.latest_workflow_conclusion || repository.latest_workflow_status" /><div><span>ÚLTIMO WORKFLOW</span><h3>{{ repository.latest_workflow_name || 'Nenhum workflow' }}</h3></div></header><p>{{ repository.latest_workflow_at ? `Atualizado ${formatRelative(repository.latest_workflow_at)}.` : 'Este projeto ainda não possui execução monitorada.' }}</p><a v-if="repository.latest_workflow_url" :href="repository.latest_workflow_url" target="_blank" rel="noopener noreferrer">Abrir execução <ExternalLink :size="13" /></a></article>
      </section>
      <section class="operation-panel">
        <nav class="tabs" aria-label="Detalhes do repositório"><button :class="{ active: activeTab === 'actions' }" @click="activeTab = 'actions'"><Play :size="16" />Actions <em>{{ repository.workflow_runs.length }}</em></button><button :class="{ active: activeTab === 'pulls' }" @click="activeTab = 'pulls'"><GitPullRequest :size="16" />Pull requests <em>{{ repository.pull_requests.length }}</em></button><button :class="{ active: activeTab === 'releases' }" @click="activeTab = 'releases'"><Box :size="16" />Releases <em>{{ repository.releases.length }}</em></button></nav>
        <div v-if="activeTab === 'actions'" class="tab-content"><div v-if="repository.workflow_runs.length" class="data-list"><article v-for="run in repository.workflow_runs" :key="run.id" class="workflow-row"><div class="row-status"><StatusBadge :value="run.conclusion || run.status" /></div><div class="row-main"><strong>{{ run.name }}</strong><span>{{ run.display_title || `${run.event || 'evento'} em ${run.head_branch || 'branch desconhecida'}` }}</span><small>#{{ run.run_number || '—' }} · tentativa {{ run.run_attempt || 1 }} · {{ formatDuration(run.duration_seconds) }}</small></div><div class="row-meta"><span>{{ formatRelative(run.github_updated_at) }}</span><code>{{ shortSha(run.head_sha) }}</code></div><div class="row-actions"><button v-if="run.status === 'in_progress' || run.status === 'queued'" class="icon-button danger" title="Cancelar" :disabled="actionRunId === run.github_id" @click="workflowAction(run, 'cancel')"><Ban :size="16" /></button><button v-if="['failure','cancelled','timed_out'].includes(run.conclusion || '')" class="icon-button" title="Reexecutar falhas" :disabled="actionRunId === run.github_id" @click="workflowAction(run, 'rerun-failed')"><RotateCcw :size="16" /></button><button class="icon-button" title="Reexecutar tudo" :disabled="actionRunId === run.github_id" @click="workflowAction(run, 'rerun')"><RefreshCw :size="16" :class="{ spin: actionRunId === run.github_id }" /></button><a class="icon-button" :href="run.html_url" target="_blank" rel="noopener noreferrer" title="Abrir no GitHub"><ExternalLink :size="16" /></a></div></article></div><EmptyState v-else :icon="Play" title="Nenhuma Action localizada" message="A sincronização exibirá as execuções mais recentes do GitHub Actions." /></div>
        <div v-else-if="activeTab === 'pulls'" class="tab-content"><div v-if="repository.pull_requests.length" class="data-list"><a v-for="pull in repository.pull_requests" :key="pull.id" :href="pull.html_url" target="_blank" rel="noopener noreferrer" class="pull-row"><div class="number">#{{ pull.number }}</div><div class="row-main"><strong>{{ pull.title }}</strong><span>{{ pull.head_ref }} → {{ pull.base_ref }}</span><small>por {{ pull.user_login || 'usuário desconhecido' }} · {{ formatRelative(pull.github_updated_at) }}</small></div><span v-if="pull.draft" class="draft-badge">Rascunho</span><ExternalLink :size="15" /></a></div><EmptyState v-else :icon="CheckCircle2" title="Nenhuma pull request aberta" message="O repositório não possui PR aberta na última sincronização." /></div>
        <div v-else class="tab-content"><div v-if="repository.releases.length" class="release-grid"><a v-for="release in repository.releases" :key="release.id" :href="release.html_url" target="_blank" rel="noopener noreferrer" class="release-card"><div class="release-icon"><Tag :size="20" /></div><div><strong>{{ release.tag_name }}</strong><span>{{ release.name || 'Release sem título' }}</span><small>{{ formatDateTime(release.published_at || release.github_created_at) }}</small></div><span v-if="release.prerelease" class="draft-badge">Pré-release</span><ExternalLink :size="15" /></a></div><EmptyState v-else :icon="Box" title="Nenhuma release publicada" message="As releases do GitHub aparecerão aqui depois da sincronização." /></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.back-link{display:inline-flex;align-items:center;gap:.4rem;width:fit-content;color:var(--text-muted);font-size:.73rem;text-decoration:none}.back-link:hover{color:var(--primary-strong)}.repository-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:1.4rem;padding:1.25rem;border:1px solid var(--border);border-radius:var(--radius-xl);background:radial-gradient(circle at 90% 10%,color-mix(in srgb,var(--primary) 11%,transparent),transparent 34%),linear-gradient(145deg,var(--surface),var(--surface-raised));box-shadow:var(--shadow-sm)}.repo-title-wrap{display:flex;gap:1rem;min-width:0}.repo-large-icon{display:grid;place-items:center;flex:0 0 auto;width:3.65rem;height:3.65rem;color:var(--primary);border-radius:1rem;background:color-mix(in srgb,var(--primary) 12%,var(--surface))}.repo-title{min-width:0}.repo-path{display:flex;gap:.3rem;color:var(--text-subtle);font-size:.7rem}.repo-title h2{margin:.25rem 0;color:var(--text-strong);font-size:clamp(1.25rem,3vw,2rem);letter-spacing:-.025em}.repo-title p{max-width:750px;margin:0;color:var(--text-muted);font-size:.8rem;line-height:1.5}.hero-badges{display:flex;align-items:center;gap:.65rem;flex-wrap:wrap;margin-top:.8rem}.hero-badges>span{display:inline-flex;align-items:center;gap:.35rem;color:var(--text-muted);font-size:.7rem}.hero-actions{display:flex;align-items:center;gap:1rem}.button-row{display:grid;gap:.45rem;min-width:145px}.error-banner{display:flex;align-items:flex-start;gap:.65rem;padding:.8rem;color:var(--danger);border:1px solid color-mix(in srgb,var(--danger) 28%,var(--border));border-radius:.8rem;background:color-mix(in srgb,var(--danger) 7%,var(--surface))}.error-banner strong{font-size:.76rem}.error-banner p{margin:.15rem 0 0;color:var(--text-muted);font-size:.68rem}.detail-stats{display:grid;grid-template-columns:repeat(5,1fr);gap:.75rem}.detail-stats article{display:flex;align-items:center;gap:.7rem;min-width:0;padding:.8rem;color:var(--primary);border:1px solid var(--border);border-radius:var(--radius-lg);background:var(--surface)}.detail-stats span{display:grid;min-width:0}.detail-stats small{color:var(--text-subtle);font-size:.6rem}.detail-stats strong{overflow:hidden;color:var(--text-strong);font-size:.88rem;text-overflow:ellipsis;white-space:nowrap}.detail-stats em{color:var(--text-muted);font-size:.58rem;font-style:normal}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.panel{padding:1rem;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--surface)}.panel header{display:flex;align-items:center;gap:.65rem;color:var(--primary)}.panel header>div{display:grid}.panel header span{color:var(--text-subtle);font-size:.6rem;font-weight:750;letter-spacing:.08em}.panel h3{margin:.08rem 0 0;color:var(--text-strong);font-size:.85rem}.panel p{min-height:2.8em;margin:.85rem 0;color:var(--text-muted);font-size:.76rem;line-height:1.5}.panel footer{display:flex;gap:1rem;flex-wrap:wrap;padding-top:.7rem;border-top:1px solid var(--border-soft)}.panel footer span,.workflow-panel a{display:inline-flex;align-items:center;gap:.35rem;color:var(--text-subtle);font-size:.66rem}.workflow-panel a{color:var(--primary-strong);text-decoration:none}.operation-panel{overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--surface)}.tabs{display:flex;gap:.2rem;overflow-x:auto;padding:.55rem;border-bottom:1px solid var(--border);background:var(--surface-raised)}.tabs button{display:inline-flex;align-items:center;gap:.45rem;padding:.62rem .8rem;color:var(--text-muted);white-space:nowrap;border:0;border-radius:.65rem;background:transparent;font:inherit;font-size:.72rem;font-weight:680;cursor:pointer}.tabs button.active{color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.tabs em{min-width:1.2rem;padding:.08rem .25rem;text-align:center;font-size:.58rem;font-style:normal;border-radius:999px;background:var(--surface-soft)}.tab-content{padding:1rem}.data-list{display:grid}.workflow-row{display:grid;grid-template-columns:auto minmax(180px,1fr) auto auto;align-items:center;gap:.8rem;padding:.85rem 0;border-bottom:1px solid var(--border-soft)}.workflow-row:last-child,.pull-row:last-child{border-bottom:0}.row-main{display:grid;min-width:0}.row-main strong{overflow:hidden;color:var(--text);font-size:.76rem;text-overflow:ellipsis;white-space:nowrap}.row-main span{overflow:hidden;color:var(--text-muted);font-size:.68rem;text-overflow:ellipsis;white-space:nowrap}.row-main small{color:var(--text-subtle);font-size:.6rem}.row-meta{display:grid;justify-items:end;gap:.2rem}.row-meta span{color:var(--text-subtle);font-size:.62rem}.row-meta code{color:var(--text-muted);font-size:.62rem}.row-actions{display:flex;gap:.3rem}.pull-row{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:.75rem;padding:.82rem 0;color:inherit;text-decoration:none;border-bottom:1px solid var(--border-soft)}.number{display:grid;place-items:center;min-width:2.8rem;height:2rem;color:var(--info);font-size:.68rem;font-weight:760;border-radius:.6rem;background:color-mix(in srgb,var(--info) 10%,var(--surface))}.draft-badge{padding:.2rem .45rem;color:var(--warning);font-size:.6rem;border-radius:999px;background:color-mix(in srgb,var(--warning) 10%,var(--surface))}.release-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.65rem}.release-card{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:.7rem;padding:.75rem;color:inherit;text-decoration:none;border:1px solid var(--border-soft);border-radius:.8rem;background:var(--surface-raised)}.release-icon{display:grid;place-items:center;width:2.3rem;height:2.3rem;color:var(--primary);border-radius:.7rem;background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.release-card>div:nth-child(2){display:grid;min-width:0}.release-card strong{color:var(--text);font-size:.76rem}.release-card span:not(.draft-badge){overflow:hidden;color:var(--text-muted);font-size:.65rem;text-overflow:ellipsis;white-space:nowrap}.release-card small{color:var(--text-subtle);font-size:.58rem}.detail-loading{display:grid;gap:1rem}.hero-skeleton{height:210px}.content-skeleton{height:500px}@media(max-width:1100px){.detail-stats{grid-template-columns:repeat(3,1fr)}.repository-hero{flex-direction:column}.hero-actions{width:100%;justify-content:space-between}.button-row{grid-template-columns:repeat(3,auto)}}@media(max-width:760px){.repo-title-wrap{align-items:flex-start}.repo-large-icon{width:2.8rem;height:2.8rem}.hero-actions{align-items:flex-start}.button-row{grid-template-columns:1fr;width:100%}.detail-stats{grid-template-columns:repeat(2,1fr)}.detail-grid{grid-template-columns:1fr}.workflow-row{grid-template-columns:1fr}.row-meta{justify-items:start}.row-actions{justify-content:flex-start}.release-grid{grid-template-columns:1fr}}@media(max-width:460px){.repository-hero{padding:1rem}.repo-title-wrap{display:grid}.hero-actions{display:grid}.detail-stats{grid-template-columns:1fr}.pull-row{grid-template-columns:auto 1fr}.pull-row>.draft-badge,.pull-row>svg{grid-column:2}}
</style>