<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertTriangle, ChevronLeft, ChevronRight, Github, Search, SlidersHorizontal, X } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import RepositoryCard from '../components/RepositoryCard.vue'
import { ApiError, api } from '../services/api'
import type { HealthStatus, PaginatedResponse, Repository } from '../types/api'

const repositories = ref<PaginatedResponse<Repository> | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const health = ref<HealthStatus | ''>('')
const privacy = ref<'all' | 'private' | 'public'>('all')
const page = ref(1)
let debounceTimer: number | undefined

function buildQuery(): string {
  const params = new URLSearchParams({ page: String(page.value), page_size: '24' })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (health.value) params.set('health', health.value)
  if (privacy.value !== 'all') params.set('private', String(privacy.value === 'private'))
  return params.toString()
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    repositories.value = await api.get<PaginatedResponse<Repository>>(`/repositories?${buildQuery()}`)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível listar os repositórios.'
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  query.value = ''
  health.value = ''
  privacy.value = 'all'
  page.value = 1
  void load()
}

function goToPage(target: number): void {
  if (!repositories.value || target < 1 || target > repositories.value.pages) return
  page.value = target
  void load()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch([health, privacy], () => {
  page.value = 1
  void load()
})
watch(query, () => {
  window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => {
    page.value = 1
    void load()
  }, 400)
})

onMounted(load)
onBeforeUnmount(() => window.clearTimeout(debounceTimer))
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">CATÁLOGO MONITORADO</span>
        <h2>Repositórios GitHub</h2>
        <p>Pesquise, filtre e acompanhe a condição operacional de cada projeto conectado.</p>
      </div>
      <div v-if="repositories" class="result-counter"><strong>{{ repositories.total }}</strong><span>projetos</span></div>
    </section>

    <section class="filter-panel">
      <label class="search-field">
        <Search :size="18" />
        <input v-model="query" type="search" placeholder="Nome, organização ou descrição…" />
        <button v-if="query" class="input-action" aria-label="Limpar pesquisa" @click="query = ''"><X :size="16" /></button>
      </label>
      <label class="select-field">
        <SlidersHorizontal :size="16" />
        <select v-model="health">
          <option value="">Todas as condições</option>
          <option value="healthy">Saudável</option>
          <option value="running">Executando</option>
          <option value="attention">Atenção</option>
          <option value="failing">Falhando</option>
          <option value="unknown">Sem CI</option>
        </select>
      </label>
      <label class="select-field">
        <Github :size="16" />
        <select v-model="privacy">
          <option value="all">Públicos e privados</option>
          <option value="private">Somente privados</option>
          <option value="public">Somente públicos</option>
        </select>
      </label>
      <button class="button ghost small" @click="resetFilters">Limpar filtros</button>
    </section>

    <div v-if="loading" class="repository-grid">
      <div v-for="index in 6" :key="index" class="skeleton repo-skeleton" />
    </div>

    <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao consultar repositórios" :message="errorMessage">
      <button class="button secondary small" @click="load">Tentar novamente</button>
    </EmptyState>

    <template v-else-if="repositories">
      <div v-if="repositories.items.length" class="repository-grid">
        <RepositoryCard v-for="repository in repositories.items" :key="repository.id" :repository="repository" />
      </div>
      <EmptyState v-else :icon="Github" title="Nenhum repositório encontrado" message="Altere os filtros ou conecte uma conta GitHub nas configurações.">
        <button class="button secondary small" @click="resetFilters">Remover filtros</button>
      </EmptyState>

      <nav v-if="repositories.pages > 1" class="pagination" aria-label="Paginação">
        <button class="icon-button" :disabled="page <= 1" aria-label="Página anterior" @click="goToPage(page - 1)"><ChevronLeft :size="18" /></button>
        <span>Página <strong>{{ page }}</strong> de {{ repositories.pages }}</span>
        <button class="icon-button" :disabled="page >= repositories.pages" aria-label="Próxima página" @click="goToPage(page + 1)"><ChevronRight :size="18" /></button>
      </nav>
    </template>
  </div>
</template>

<style scoped>
.result-counter { display:grid; justify-items:end; }.result-counter strong{color:var(--text-strong);font-size:1.45rem}.result-counter span{color:var(--text-subtle);font-size:.68rem}
.filter-panel { display:grid; grid-template-columns:minmax(250px,1fr) auto auto auto; align-items:center; gap:.7rem; padding:.8rem; border:1px solid var(--border); border-radius:var(--radius-xl); background:var(--surface); }
.search-field,.select-field { display:flex; align-items:center; gap:.55rem; min-height:2.65rem; padding:0 .75rem; color:var(--text-subtle); border:1px solid var(--border); border-radius:.78rem; background:var(--surface-raised); }
.search-field:focus-within,.select-field:focus-within { border-color:color-mix(in srgb,var(--primary) 55%,var(--border)); box-shadow:0 0 0 3px color-mix(in srgb,var(--primary) 10%,transparent); }
.search-field input,.select-field select { width:100%; min-width:0; color:var(--text); border:0; outline:0; background:transparent; font:inherit; font-size:.78rem; }
.select-field select { min-width:160px; cursor:pointer; }
.repository-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }.repo-skeleton{height:315px}
.pagination { display:flex; align-items:center; justify-content:center; gap:.8rem; }.pagination span{color:var(--text-muted);font-size:.73rem}.pagination strong{color:var(--text-strong)}
@media(max-width:1200px){.repository-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-panel{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}}
@media(max-width:680px){.repository-grid{grid-template-columns:1fr}.filter-panel{grid-template-columns:1fr}.search-field{grid-column:auto}.select-field select{min-width:0}.filter-panel>.button{width:100%}}
</style>
