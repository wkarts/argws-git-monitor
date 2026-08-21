<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  AlertTriangle, Ban, Clock3, ExternalLink, GitBranch, Globe2, LockKeyhole,
  PlayCircle, RefreshCw, RotateCcw, Search
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import OperationStatusBanner from '../components/OperationStatusBanner.vue'
import PaginationBar from '../components/PaginationBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../services/api'
import { formatDuration, formatRelative, shortSha } from '../services/format'
import { useToastStore } from '../stores/toast'
import type { OperationWorkflow, PaginatedResponse, WorkflowActionResponse } from '../types/api'

const toasts = useToastStore()
const response = ref<PaginatedResponse<OperationWorkflow> | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const state = ref('')
const page = ref(1)
const actionRunId = ref<number | null>(null)
let debounceTimer: number | undefined

function buildQuery(): string {
  const params = new URLSearchParams({ page: String(page.value), page_size: '30' })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (state.value) params.set('state', state.value)
  return params.toString()
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try { response.value = await api.get<PaginatedResponse<OperationWorkflow>>(`/operations/actions?${buildQuery()}`) }
  catch (error) { errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível carregar as execuções.' }
  finally { loading.value = false }
}

async function workflowAction(run: OperationWorkflow, action: 'cancel' | 'rerun' | 'rerun-failed'): Promise<void> {
  actionRunId.value = run.github_id
  try {
    const result = await api.post<WorkflowActionResponse>(`/repositories/${run.repository_id}/workflow-runs/${run.github_id}/${action}`)
    toasts.success('Solicitação enviada', result.message)
    window.setTimeout(() => void load(), 2500)
  } catch (error) { toasts.error('Não foi possível operar o workflow', error instanceof ApiError ? error.message : undefined) }
  finally { actionRunId.value = null }
}

function isRunning(run: OperationWorkflow): boolean { return ['queued','in_progress','waiting','pending'].includes(run.status) }
function isFailure(run: OperationWorkflow): boolean { return ['failure','cancelled','timed_out','action_required','startup_failure'].includes(run.conclusion || '') }
function changePage(target: number): void { page.value=target; void load(); window.scrollTo({top:0,behavior:'smooth'}) }
watch(state,()=>{page.value=1;void load()})
watch(query,()=>{window.clearTimeout(debounceTimer);debounceTimer=window.setTimeout(()=>{page.value=1;void load()},350)})
onMounted(load)
onBeforeUnmount(()=>window.clearTimeout(debounceTimer))
</script>

<template>
  <div class="operations-page">
    <section class="operations-heading"><div class="operations-heading-copy"><span>GITHUB ACTIONS</span><h2>Execuções e pipelines</h2><p>Acompanhe builds, duração, branches e opere reexecuções ou cancelamentos sem sair do monitor.</p></div><div v-if="response" class="operations-counter"><strong>{{ response.total }}</strong><span>execuções</span></div></section>
    <OperationStatusBanner module-key="actions" @refreshed="load" />
    <section class="operations-filter-panel"><label class="operations-search"><Search :size="16" /><input v-model="query" type="search" placeholder="Buscar workflow, repositório ou branch..." /></label><select v-model="state" aria-label="Filtrar resultado"><option value="">Todos os estados</option><option value="running">Executando</option><option value="success">Sucesso</option><option value="failure">Falhou</option></select><button class="button secondary compact" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />Atualizar</button></section>
    <section class="operations-panel">
      <div v-if="loading" class="operations-loading"><div v-for="index in 6" :key="index" class="skeleton" /></div>
      <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao carregar Actions" :message="errorMessage"><button class="button secondary compact" @click="load"><RefreshCw :size="15" />Tentar novamente</button></EmptyState>
      <EmptyState v-else-if="!response?.items.length" :icon="PlayCircle" title="Nenhuma execução coletada" message="Veja acima se a API do GitHub Actions foi observada. Se a cobertura estiver abaixo de 100%, sincronize e confira Fila/permissões." />
      <template v-else-if="response">
        <div class="operations-table-wrap"><table class="operations-table actions-table"><thead><tr><th>Repositório</th><th>Workflow</th><th>Status</th><th>Branch / commit</th><th>Duração</th><th>Atualização</th><th aria-label="Ações" /></tr></thead><tbody><tr v-for="run in response.items" :key="run.id"><td><RouterLink :to="`/repositories/${run.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="run.repository_private" :size="14" /><Globe2 v-else :size="14" /></span><span><strong>{{ run.repository_full_name.split('/').at(-1) }}</strong><small>{{ run.repository_full_name.split('/')[0] }}</small></span></RouterLink></td><td><div class="operation-main"><strong>{{ run.name }}</strong><span>{{ run.display_title || `Execução #${run.run_number || '—'}` }}</span><small>{{ run.event || 'evento não informado' }} · tentativa {{ run.run_attempt || 1 }}</small></div></td><td><StatusBadge :value="run.conclusion || run.status" compact /></td><td><div class="run-reference"><span><GitBranch :size="13" />{{ run.head_branch || '—' }}</span><code>{{ shortSha(run.head_sha) }}</code></div></td><td><span class="duration-cell"><Clock3 :size="13" />{{ formatDuration(run.duration_seconds) }}</span></td><td>{{ formatRelative(run.github_updated_at || run.github_created_at) }}</td><td><div class="operation-actions"><button v-if="isRunning(run)" class="operation-action-button danger" title="Cancelar workflow" :disabled="actionRunId === run.github_id" @click="workflowAction(run,'cancel')"><Ban :size="15" /></button><button v-if="isFailure(run)" class="operation-action-button" title="Reexecutar jobs com falha" :disabled="actionRunId === run.github_id" @click="workflowAction(run,'rerun-failed')"><RotateCcw :size="15" /></button><button class="operation-action-button" title="Reexecutar workflow" :disabled="actionRunId === run.github_id" @click="workflowAction(run,'rerun')"><RefreshCw :size="15" :class="{spin:actionRunId===run.github_id}" /></button><a class="operation-action-button" :href="run.html_url" target="_blank" rel="noopener noreferrer" title="Abrir no GitHub"><ExternalLink :size="15" /></a></div></td></tr></tbody></table></div>
        <div class="operations-mobile-list"><article v-for="run in response.items" :key="run.id" class="operation-mobile-card"><div class="operation-mobile-card-header"><RouterLink :to="`/repositories/${run.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="run.repository_private" :size="14" /><Globe2 v-else :size="14" /></span><span><strong>{{ run.repository_full_name.split('/').at(-1) }}</strong><small>{{ run.repository_full_name.split('/')[0] }}</small></span></RouterLink><StatusBadge :value="run.conclusion || run.status" compact /></div><div class="operation-mobile-card-body"><strong>{{ run.name }}</strong><span>{{ run.display_title || `Execução #${run.run_number || '—'}` }}</span><small>{{ run.head_branch || '—' }} · {{ shortSha(run.head_sha) }} · {{ formatDuration(run.duration_seconds) }}</small></div><div class="operation-mobile-card-footer"><span>{{ formatRelative(run.github_updated_at || run.github_created_at) }}</span><div class="operation-actions"><button v-if="isRunning(run)" class="operation-action-button danger" aria-label="Cancelar workflow" :disabled="actionRunId===run.github_id" @click="workflowAction(run,'cancel')"><Ban :size="15" /></button><button v-if="isFailure(run)" class="operation-action-button" aria-label="Reexecutar falhas" :disabled="actionRunId===run.github_id" @click="workflowAction(run,'rerun-failed')"><RotateCcw :size="15" /></button><button class="operation-action-button" aria-label="Reexecutar workflow" :disabled="actionRunId===run.github_id" @click="workflowAction(run,'rerun')"><RefreshCw :size="15" :class="{spin:actionRunId===run.github_id}" /></button><a class="operation-action-button" :href="run.html_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15" /></a></div></div></article></div>
        <PaginationBar :page="response.page" :pages="response.pages" :total="response.total" @change="changePage" />
      </template>
    </section>
  </div>
</template>

<style scoped>
.run-reference{display:grid;gap:.18rem}.run-reference span,.duration-cell{display:inline-flex;align-items:center;gap:.3rem;color:var(--text-muted);font-size:.61rem}.run-reference code{color:var(--text-subtle);font-size:.56rem}
</style>
