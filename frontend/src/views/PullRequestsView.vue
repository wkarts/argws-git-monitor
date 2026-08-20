<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  AlertTriangle,
  ExternalLink,
  GitBranch,
  GitPullRequest,
  Globe2,
  LockKeyhole,
  RefreshCw,
  Search,
  UserRound
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import PaginationBar from '../components/PaginationBar.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import type { OperationPullRequest, PaginatedResponse } from '../types/api'

const response = ref<PaginatedResponse<OperationPullRequest> | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const mode = ref('')
const page = ref(1)
let debounceTimer: number | undefined

function buildQuery(): string {
  const params = new URLSearchParams({ page: String(page.value), page_size: '30' })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (mode.value === 'draft') params.set('draft', 'true')
  if (mode.value === 'ready') params.set('draft', 'false')
  return params.toString()
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    response.value = await api.get<PaginatedResponse<OperationPullRequest>>(`/operations/pull-requests?${buildQuery()}`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível carregar as pull requests.'
  } finally {
    loading.value = false
  }
}

function changePage(target: number): void {
  page.value = target
  void load()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch(mode, () => {
  page.value = 1
  void load()
})
watch(query, () => {
  window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => {
    page.value = 1
    void load()
  }, 350)
})

onMounted(load)
onBeforeUnmount(() => window.clearTimeout(debounceTimer))
</script>

<template>
  <div class="operations-page">
    <section class="operations-heading">
      <div class="operations-heading-copy">
        <span>COLABORAÇÃO</span>
        <h2>Pull Requests abertas</h2>
        <p>Consolide revisões, branches de origem e responsáveis de todos os projetos monitorados.</p>
      </div>
      <div v-if="response" class="operations-counter"><strong>{{ response.total }}</strong><span>PRs abertas</span></div>
    </section>

    <section class="operations-filter-panel">
      <label class="operations-search"><Search :size="16" /><input v-model="query" type="search" placeholder="Buscar título, repositório, branch ou autor..." /></label>
      <select v-model="mode" aria-label="Filtrar pull requests">
        <option value="">Todas as PRs</option>
        <option value="ready">Prontas para revisão</option>
        <option value="draft">Rascunhos</option>
      </select>
      <button class="button secondary compact" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />Atualizar</button>
    </section>

    <section class="operations-panel">
      <div v-if="loading" class="operations-loading"><div v-for="index in 6" :key="index" class="skeleton" /></div>
      <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao carregar Pull Requests" :message="errorMessage">
        <button class="button secondary compact" @click="load"><RefreshCw :size="15" />Tentar novamente</button>
      </EmptyState>
      <EmptyState v-else-if="!response?.items.length" :icon="GitPullRequest" title="Nenhuma pull request aberta" message="As PRs aparecerão após a sincronização dos repositórios." />

      <template v-else-if="response">
        <div class="operations-table-wrap">
          <table class="operations-table">
            <thead><tr><th>Repositório</th><th>Pull Request</th><th>Fluxo de branches</th><th>Autor</th><th>Atualização</th><th aria-label="Ações" /></tr></thead>
            <tbody>
              <tr v-for="pull in response.items" :key="pull.id">
                <td>
                  <RouterLink :to="`/repositories/${pull.repository_id}`" class="operation-repository">
                    <span class="operation-privacy"><LockKeyhole v-if="pull.repository_private" :size="14" /><Globe2 v-else :size="14" /></span>
                    <span><strong>{{ pull.repository_full_name.split('/').at(-1) }}</strong><small>{{ pull.repository_full_name.split('/')[0] }}</small></span>
                  </RouterLink>
                </td>
                <td><div class="operation-main"><strong>#{{ pull.number }} · {{ pull.title }}</strong><span>{{ pull.draft ? 'Rascunho' : 'Aberta para revisão' }}</span><small>{{ pull.mergeable_state || 'estado de merge não informado' }}</small></div></td>
                <td><div class="branch-flow"><span><GitBranch :size="13" />{{ pull.head_ref || '—' }}</span><i>→</i><code>{{ pull.base_ref || '—' }}</code></div></td>
                <td><span class="author-cell"><UserRound :size="13" />{{ pull.user_login || 'desconhecido' }}</span></td>
                <td>{{ formatRelative(pull.github_updated_at || pull.github_created_at) }}</td>
                <td><div class="operation-actions"><a class="operation-action-button" :href="pull.html_url" target="_blank" rel="noopener noreferrer" title="Abrir no GitHub"><ExternalLink :size="15" /></a></div></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="operations-mobile-list">
          <article v-for="pull in response.items" :key="pull.id" class="operation-mobile-card">
            <div class="operation-mobile-card-header">
              <RouterLink :to="`/repositories/${pull.repository_id}`" class="operation-repository">
                <span class="operation-privacy"><LockKeyhole v-if="pull.repository_private" :size="14" /><Globe2 v-else :size="14" /></span>
                <span><strong>{{ pull.repository_full_name.split('/').at(-1) }}</strong><small>{{ pull.repository_full_name.split('/')[0] }}</small></span>
              </RouterLink>
              <span class="pr-mode" :class="{ draft: pull.draft }">{{ pull.draft ? 'Rascunho' : 'Aberta' }}</span>
            </div>
            <div class="operation-mobile-card-body"><strong>#{{ pull.number }} · {{ pull.title }}</strong><span>{{ pull.head_ref || '—' }} → {{ pull.base_ref || '—' }}</span><small>por {{ pull.user_login || 'desconhecido' }} · {{ formatRelative(pull.github_updated_at || pull.github_created_at) }}</small></div>
            <div class="operation-mobile-card-footer"><span>{{ pull.mergeable_state || 'estado de merge não informado' }}</span><a class="operation-action-button" :href="pull.html_url" target="_blank" rel="noopener noreferrer" aria-label="Abrir no GitHub"><ExternalLink :size="15" /></a></div>
          </article>
        </div>

        <PaginationBar :page="response.page" :pages="response.pages" :total="response.total" @change="changePage" />
      </template>
    </section>
  </div>
</template>

<style scoped>
.branch-flow,.author-cell { display: inline-flex; align-items: center; gap: 0.32rem; color: var(--text-muted); font-size: 0.61rem; }
.branch-flow { flex-wrap: wrap; }
.branch-flow i { color: var(--text-subtle); font-style: normal; }
.branch-flow code { color: var(--primary-strong); font-size: 0.58rem; }
.pr-mode { padding: 0.18rem 0.45rem; color: var(--success); border-radius: 999px; background: color-mix(in srgb, var(--success) 9%, var(--surface)); font-size: 0.55rem; font-weight: 780; }
.pr-mode.draft { color: var(--warning); background: color-mix(in srgb, var(--warning) 9%, var(--surface)); }
</style>
