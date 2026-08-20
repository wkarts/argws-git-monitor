<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  AlertTriangle,
  CircleDotDashed,
  ExternalLink,
  Globe2,
  LockKeyhole,
  RefreshCw,
  Search
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import HealthRing from '../components/HealthRing.vue'
import PaginationBar from '../components/PaginationBar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import type { IssueSummary, PaginatedResponse } from '../types/api'

const response = ref<PaginatedResponse<IssueSummary> | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const page = ref(1)
let debounceTimer: number | undefined

function buildQuery(): string {
  const params = new URLSearchParams({ page: String(page.value), page_size: '30' })
  if (query.value.trim()) params.set('q', query.value.trim())
  return params.toString()
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    response.value = await api.get<PaginatedResponse<IssueSummary>>(`/operations/issues?${buildQuery()}`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível carregar o resumo de issues.'
  } finally {
    loading.value = false
  }
}

function changePage(target: number): void {
  page.value = target
  void load()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

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
        <span>ACOMPANHAMENTO</span>
        <h2>Issues abertas por projeto</h2>
        <p>Identifique rapidamente os repositórios com maior volume de pendências e abra a triagem no GitHub.</p>
      </div>
      <div v-if="response" class="operations-counter"><strong>{{ response.total }}</strong><span>projetos</span></div>
    </section>

    <section class="operations-filter-panel">
      <label class="operations-search"><Search :size="16" /><input v-model="query" type="search" placeholder="Buscar repositório..." /></label>
      <button class="button secondary compact" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />Atualizar</button>
    </section>

    <section class="operations-panel">
      <div v-if="loading" class="operations-loading"><div v-for="index in 6" :key="index" class="skeleton" /></div>
      <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao carregar Issues" :message="errorMessage">
        <button class="button secondary compact" @click="load"><RefreshCw :size="15" />Tentar novamente</button>
      </EmptyState>
      <EmptyState v-else-if="!response?.items.length" :icon="CircleDotDashed" title="Nenhuma issue aberta" message="Nenhum repositório monitorado possui issue aberta neste momento." />

      <template v-else-if="response">
        <div class="operations-table-wrap">
          <table class="operations-table">
            <thead><tr><th>Repositório</th><th>Issues abertas</th><th>Saúde</th><th>Índice</th><th>Última sincronização</th><th aria-label="Ações" /></tr></thead>
            <tbody>
              <tr v-for="item in response.items" :key="item.repository_id">
                <td>
                  <RouterLink :to="`/repositories/${item.repository_id}`" class="operation-repository">
                    <span class="operation-privacy"><LockKeyhole v-if="item.repository_private" :size="14" /><Globe2 v-else :size="14" /></span>
                    <span><strong>{{ item.repository_full_name.split('/').at(-1) }}</strong><small>{{ item.repository_full_name.split('/')[0] }}</small></span>
                  </RouterLink>
                </td>
                <td><span class="operation-count-pill">{{ item.open_issue_count }}</span></td>
                <td><StatusBadge :value="item.health_status" health compact /></td>
                <td><HealthRing :score="item.health_score" :size="44" /></td>
                <td>{{ formatRelative(item.last_synced_at) }}</td>
                <td><div class="operation-actions"><a class="operation-action-button" :href="`${item.repository_html_url}/issues`" target="_blank" rel="noopener noreferrer" title="Abrir issues no GitHub"><ExternalLink :size="15" /></a></div></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="operations-mobile-list">
          <article v-for="item in response.items" :key="item.repository_id" class="operation-mobile-card">
            <div class="operation-mobile-card-header">
              <RouterLink :to="`/repositories/${item.repository_id}`" class="operation-repository">
                <span class="operation-privacy"><LockKeyhole v-if="item.repository_private" :size="14" /><Globe2 v-else :size="14" /></span>
                <span><strong>{{ item.repository_full_name.split('/').at(-1) }}</strong><small>{{ item.repository_full_name.split('/')[0] }}</small></span>
              </RouterLink>
              <span class="operation-count-pill">{{ item.open_issue_count }}</span>
            </div>
            <div class="issues-mobile-health"><HealthRing :score="item.health_score" :size="48" /><div><StatusBadge :value="item.health_status" health compact /><small>Sincronizado {{ formatRelative(item.last_synced_at) }}</small></div></div>
            <div class="operation-mobile-card-footer"><span>Abrir triagem completa</span><a class="operation-action-button" :href="`${item.repository_html_url}/issues`" target="_blank" rel="noopener noreferrer" aria-label="Abrir issues no GitHub"><ExternalLink :size="15" /></a></div>
          </article>
        </div>

        <PaginationBar :page="response.page" :pages="response.pages" :total="response.total" @change="changePage" />
      </template>
    </section>
  </div>
</template>

<style scoped>
.issues-mobile-health { display: flex; align-items: center; gap: 0.65rem; }
.issues-mobile-health > div { display: grid; gap: 0.28rem; }
.issues-mobile-health small { color: var(--text-subtle); font-size: 0.56rem; }
</style>
