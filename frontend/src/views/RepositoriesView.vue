<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertTriangle, Ban, ChevronLeft, ChevronRight, Clock3, Github, Plus, Search, SlidersHorizontal, Wrench, X } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import RepositoryCard from '../components/RepositoryCard.vue'
import { ApiError, api } from '../services/api'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import { useToastStore } from '../stores/toast'
import type { GitHubConnection, HealthStatus, PaginatedResponse, Repository } from '../types/api'

interface BlacklistItem { repository_id:string }

const toasts = useToastStore()
const repositories = ref<PaginatedResponse<Repository> | null>(null)
const connections = ref<GitHubConnection[]>([])
const blacklistCount = ref(0)
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const health = ref<HealthStatus | ''>('')
const privacy = ref<'all' | 'private' | 'public'>('all')
const page = ref(1)
const showCreate = ref(false)
const creating = ref(false)
const createForm = reactive({ connection_id: '', name: '', description: '', private: true, auto_init: true })
let debounceTimer: number | undefined
let realtimeTimer: number | undefined

const usableConnections = computed(() => connections.value.filter((item) => item.status === 'active'))

function buildQuery(): string {
  const params = new URLSearchParams({ page: String(page.value), page_size: '24', monitoring_enabled: 'true' })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (health.value) params.set('health', health.value)
  if (privacy.value !== 'all') params.set('private', String(privacy.value === 'private'))
  return params.toString()
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [repoData, connectionData, ignored] = await Promise.all([
      api.get<PaginatedResponse<Repository>>(`/repositories?${buildQuery()}`),
      api.get<GitHubConnection[]>('/github/connections'),
      api.get<BlacklistItem[]>('/repository-controls/blacklist')
    ])
    repositories.value = repoData
    connections.value = connectionData
    blacklistCount.value = ignored.length
    if (!createForm.connection_id && usableConnections.value[0]) createForm.connection_id = usableConnections.value[0].id
  } catch (error) { errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível listar os repositórios.' }
  finally { loading.value = false }
}

async function createRepository(): Promise<void> {
  if (!createForm.connection_id || !createForm.name.trim()) return
  creating.value = true
  try {
    const created = await api.post<Repository>(`/github/connections/${createForm.connection_id}/repositories`, {
      name: createForm.name.trim(), description: createForm.description.trim() || null, private: createForm.private, auto_init: createForm.auto_init
    })
    toasts.success('Repositório criado', `${created.full_name} já foi incluído no monitor; os eventos seguintes chegarão em tempo real.`)
    Object.assign(createForm, { connection_id: usableConnections.value[0]?.id || '', name: '', description: '', private: true, auto_init: true })
    showCreate.value = false
    await load()
  } catch (error) { toasts.error('Não foi possível criar no GitHub', error instanceof ApiError ? error.message : undefined) }
  finally { creating.value = false }
}

function handleRealtime(event: Event): void {
  const detail = (event as CustomEvent<RealtimeEvent>).detail
  if (!detail || (!detail.type.startsWith('github.') && !detail.type.startsWith('repository.'))) return
  window.clearTimeout(realtimeTimer)
  realtimeTimer = window.setTimeout(() => void load(), 180)
}

function resetFilters(): void { query.value=''; health.value=''; privacy.value='all'; page.value=1; void load() }
function goToPage(target: number): void { if (!repositories.value || target<1 || target>repositories.value.pages) return; page.value=target; void load(); window.scrollTo({top:0,behavior:'smooth'}) }
watch([health,privacy],()=>{page.value=1;void load()})
watch(query,()=>{window.clearTimeout(debounceTimer);debounceTimer=window.setTimeout(()=>{page.value=1;void load()},400)})
onMounted(() => { window.addEventListener(REALTIME_EVENT, handleRealtime); void load() })
onBeforeUnmount(()=>{ window.clearTimeout(debounceTimer); window.clearTimeout(realtimeTimer); window.removeEventListener(REALTIME_EVENT, handleRealtime) })
</script>

<template>
  <div class="page-stack repositories-page">
    <section class="page-heading">
      <div><span class="eyebrow">CATÁLOGO MONITORADO</span><h2>Repositórios GitHub</h2><p>Pesquise, filtre, sincronize, altere visibilidade e gerencie cada projeto conectado.</p></div>
      <div class="heading-actions">
        <div v-if="repositories" class="result-counter"><strong>{{repositories.total}}</strong><span>monitorados</span></div>
        <RouterLink class="button ignored-button" to="/repositories/blacklist"><Ban :size="16"/><span>Ignorados</span><em v-if="blacklistCount">{{blacklistCount}}</em></RouterLink>
        <RouterLink class="button secondary" to="/github-tools"><Wrench :size="16"/>GitHub Tools</RouterLink>
        <RouterLink class="button secondary" to="/inactivity"><Clock3 :size="16"/>Inatividade</RouterLink>
        <button class="button primary" :disabled="!usableConnections.length" @click="showCreate=true"><Plus :size="16"/>Novo repositório</button>
      </div>
    </section>

    <section v-if="blacklistCount" class="info-callout ignored-callout"><Ban :size="18"/><div><strong>{{blacklistCount}} repositório(s) ignorado(s)</strong><p>Eles estão ocultos desta listagem e não reaparecem nas sincronizações. Abra “Ignorados” para revisar ou reativar.</p></div><RouterLink class="button ghost compact" to="/repositories/blacklist">Abrir lista</RouterLink></section>

    <section v-if="showCreate" class="create-panel"><header><div><span class="eyebrow">CRIAR NO GITHUB</span><h3>Novo repositório</h3></div><button class="icon-button" @click="showCreate=false"><X :size="17"/></button></header><form @submit.prevent="createRepository"><label class="field"><span>Conta GitHub</span><select v-model="createForm.connection_id" required><option v-for="connection in usableConnections" :key="connection.id" :value="connection.id">@{{connection.github_login}} · {{connection.name}}</option></select></label><label class="field"><span>Nome</span><input v-model="createForm.name" placeholder="meu-projeto" required/></label><label class="field wide"><span>Descrição</span><input v-model="createForm.description" maxlength="350"/></label><label class="check-option"><input v-model="createForm.private" type="checkbox"/><span>Privado</span></label><label class="check-option"><input v-model="createForm.auto_init" type="checkbox"/><span>Inicializar README</span></label><button class="button primary" :disabled="creating">{{creating?'Criando…':'Criar e monitorar'}}</button></form><p>Para criar ou alterar repositórios, o token precisa da permissão <strong>Administration: write</strong>.</p></section>

    <section class="filter-panel"><label class="search-field"><Search :size="18"/><input v-model="query" type="search" placeholder="Nome, organização ou descrição…"/><button v-if="query" class="input-action" aria-label="Limpar pesquisa" @click="query='' "><X :size="16"/></button></label><label class="select-field"><SlidersHorizontal :size="16"/><select v-model="health"><option value="">Todas as condições</option><option value="healthy">Saudável</option><option value="running">Executando</option><option value="attention">Atenção</option><option value="failing">Falhando</option><option value="unknown">Aguardando dados</option></select></label><label class="select-field"><Github :size="16"/><select v-model="privacy"><option value="all">Públicos e privados</option><option value="private">Somente privados</option><option value="public">Somente públicos</option></select></label><button class="button ghost compact" @click="resetFilters">Limpar filtros</button></section>

    <div v-if="loading" class="repository-grid"><div v-for="n in 6" :key="n" class="skeleton repo-skeleton"/></div>
    <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao consultar repositórios" :message="errorMessage"><button class="button secondary compact" @click="load">Tentar novamente</button></EmptyState>
    <template v-else-if="repositories"><div v-if="repositories.items.length" class="repository-grid"><RepositoryCard v-for="repository in repositories.items" :key="repository.id" :repository="repository" @changed="load"/></div><EmptyState v-else :icon="Github" title="Nenhum repositório encontrado" message="Se a conta GitHub já está conectada, abra Configurações > Projetos e marque o que deseja monitorar."><button class="button secondary compact" @click="resetFilters">Remover filtros</button></EmptyState><nav v-if="repositories.pages>1" class="pagination"><button class="icon-button" :disabled="page<=1" @click="goToPage(page-1)"><ChevronLeft :size="18"/></button><span>Página <strong>{{page}}</strong> de {{repositories.pages}}</span><button class="icon-button" :disabled="page>=repositories.pages" @click="goToPage(page+1)"><ChevronRight :size="18"/></button></nav></template>
  </div>
</template>

<style scoped>
.heading-actions{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap}.result-counter{display:grid;justify-items:end}.result-counter strong{color:var(--text-strong);font-size:1.45rem}.result-counter span{color:var(--text-muted);font-size:.68rem}.ignored-button{position:relative;color:var(--warning);border-color:color-mix(in srgb,var(--warning) 30%,var(--border));background:color-mix(in srgb,var(--warning) 7%,var(--surface));box-shadow:none}.ignored-button em{display:grid;place-items:center;min-width:1.25rem;height:1.25rem;padding:0 .28rem;color:#fff;border-radius:999px;background:var(--warning);font-size:.58rem;font-style:normal;font-weight:850}.ignored-callout{align-items:center}.ignored-callout>div{flex:1}.create-panel{padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.create-panel header{display:flex;align-items:center;justify-content:space-between}.create-panel h3{margin:.1rem 0;color:var(--text-strong)}.create-panel form{display:grid;grid-template-columns:1fr 1fr 2fr auto auto auto;align-items:end;gap:.6rem;margin-top:.8rem}.check-option{display:flex;align-items:center;gap:.4rem;min-height:2.65rem;color:var(--text);font-size:.68rem}.create-panel>p{margin:.65rem 0 0;color:var(--text-muted);font-size:.65rem}.filter-panel{display:grid;grid-template-columns:minmax(250px,1fr) auto auto auto;align-items:center;gap:.7rem;padding:.8rem}.search-field,.select-field{display:flex;align-items:center;gap:.55rem;min-height:2.65rem;padding:0 .75rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.78rem;background:var(--surface-raised)}.search-field input,.select-field select{width:100%;min-width:0;color:var(--text);border:0;outline:0;background:transparent;font:inherit;font-size:.78rem}.select-field select{min-width:160px;cursor:pointer}.repository-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}.repo-skeleton{height:355px;border-radius:1rem}.pagination{display:flex;align-items:center;justify-content:center;gap:.8rem}.pagination span{color:var(--text-muted);font-size:.73rem}.pagination strong{color:var(--text-strong)}
@media(max-width:1250px){.repository-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.filter-panel{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}.create-panel form{grid-template-columns:1fr 1fr}.create-panel .wide{grid-column:1/-1}}@media(max-width:680px){.repository-grid{grid-template-columns:1fr}.filter-panel,.create-panel form{grid-template-columns:1fr}.search-field,.create-panel .wide{grid-column:auto}.select-field select{min-width:0}.heading-actions{align-items:stretch;flex-direction:column}.result-counter{justify-items:start}.page-heading{align-items:stretch}.create-panel form>.button,.heading-actions>.button{width:100%}.ignored-callout{align-items:stretch;flex-direction:column}.ignored-callout .button{width:100%}}
</style>
