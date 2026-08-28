<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Ban, ChevronLeft, RefreshCw, RotateCcw, Search, ShieldBan, X } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'

interface BlacklistItem {
  repository_id: string
  github_id: number
  full_name: string
  connection_id: string
  connection_name: string
  blacklisted_at: string | null
  reason: string | null
}

const dialogs = useDialogStore()
const toasts = useToastStore()
const loading = ref(true)
const items = ref<BlacklistItem[]>([])
const busy = ref('')
const query = ref('')

const filteredItems = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return items.value
  return items.value.filter((item) => [item.full_name, item.connection_name, item.reason || '', String(item.github_id)].some((value) => value.toLowerCase().includes(term)))
})
const connectionsCount = computed(() => new Set(items.value.map((item) => item.connection_id)).size)
function when(value: string | null): string { return value ? new Date(value).toLocaleString('pt-BR') : '—' }

async function load(): Promise<void> {
  loading.value = true
  try { items.value = await api.get<BlacklistItem[]>('/repository-controls/blacklist') }
  catch (error) { toasts.error('Falha ao carregar repositórios ignorados', error instanceof ApiError ? error.message : undefined) }
  finally { loading.value = false }
}

async function restore(item: BlacklistItem): Promise<void> {
  const accepted = await dialogs.askConfirmation({
    title: 'Reativar repositório?',
    message: `${item.full_name} será removido da lista de ignorados e voltará a participar do monitoramento e das próximas sincronizações.`,
    tone: 'info',
    confirmLabel: 'Reativar monitoramento',
  })
  if (!accepted) return
  busy.value = item.repository_id
  try {
    await api.delete(`/repository-controls/${item.repository_id}/blacklist`)
    toasts.success('Repositório reativado', `${item.full_name} voltou ao monitoramento.`)
    await load()
  } catch (error) { toasts.error('Falha ao reativar', error instanceof ApiError ? error.message : undefined) }
  finally { busy.value = '' }
}

onMounted(load)
</script>

<template>
  <div class="page-stack blacklist-page">
    <section class="hero-panel blacklist-hero"><div><span class="eyebrow">REPOSITÓRIOS IGNORADOS</span><h2>Lista de exclusão persistente</h2><p>Todo repositório ignorado fica registrado aqui e não reaparece depois das sincronizações com o GitHub. Esta é a área para revisar ou reativar projetos removidos do monitoramento.</p><div class="button-row hero-actions"><RouterLink class="button secondary" to="/repositories"><ChevronLeft :size="16"/>Voltar aos repositórios</RouterLink><button class="button ghost" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button></div></div><div class="metric-grid hero-metrics"><article class="metric-card"><span>Ignorados</span><strong>{{items.length}}</strong><small>tombstones persistentes</small></article><article class="metric-card"><span>Conexões</span><strong>{{connectionsCount}}</strong><small>contas GitHub envolvidas</small></article><article class="metric-card"><span>Visíveis no monitor</span><strong>0</strong><small>enquanto permanecerem aqui</small></article><article class="metric-card"><span>Reimportação</span><strong>OFF</strong><small>bloqueada pelo tombstone</small></article></div></section>
    <section class="info-callout"><ShieldBan :size="20"/><div><strong>Onde encontrar esta tela</strong><p>Ela também fica acessível em Repositórios → Ignorados. Restaurar um item remove o bloqueio persistente e volta a habilitar seu monitoramento.</p></div></section>
    <section class="panel search-panel"><label class="search-field"><Search :size="17"/><input v-model="query" type="search" placeholder="Buscar repositório, conexão ou motivo…"/><button v-if="query" class="input-action" aria-label="Limpar busca" @click="query='' "><X :size="15"/></button></label><span class="soft-pill">{{filteredItems.length}} de {{items.length}}</span></section>
    <section class="panel table-panel desktop-table"><header><div><strong>Ignorados persistentemente</strong><span>O registro local é preservado justamente para impedir o retorno automático após sync.</span></div><Ban :size="19"/></header><div class="table-wrap"><table><thead><tr><th>Repositório</th><th>Conexão</th><th>Motivo</th><th>Ignorado em</th><th>Ação</th></tr></thead><tbody><tr v-for="item in filteredItems" :key="item.repository_id"><td><strong>{{item.full_name}}</strong><small>GitHub #{{item.github_id}}</small></td><td>{{item.connection_name}}</td><td>{{item.reason||'Ignorado pelo usuário.'}}</td><td>{{when(item.blacklisted_at)}}</td><td><button class="button secondary compact" :disabled="busy===item.repository_id" @click="restore(item)"><RotateCcw :size="14"/>Reativar</button></td></tr><tr v-if="!loading&&!filteredItems.length"><td colspan="5" class="empty">{{items.length?'Nenhum item corresponde à busca.':'Nenhum repositório ignorado.'}}</td></tr></tbody></table></div></section>
    <div class="mobile-cards"><article v-for="item in filteredItems" :key="item.repository_id" class="resource-card"><div class="resource-card-head"><div><strong>{{item.full_name}}</strong><small>{{item.connection_name}} · GitHub #{{item.github_id}}</small></div><span class="status-pill warn"><Ban :size="11"/>Ignorado</span></div><p class="reason">{{item.reason||'Ignorado pelo usuário.'}}</p><div class="item-meta"><span>Desde<strong>{{when(item.blacklisted_at)}}</strong></span></div><button class="button secondary full" :disabled="busy===item.repository_id" @click="restore(item)"><RotateCcw :size="14"/>Restaurar ao monitor</button></article><div v-if="!loading&&!filteredItems.length" class="resource-card empty-card">{{items.length?'Nenhum item corresponde à busca.':'Nenhum repositório ignorado.'}}</div></div>
  </div>
</template>

<style scoped>
.blacklist-hero{align-items:center}.hero-actions{margin-top:1rem}.hero-metrics{align-self:stretch}.search-panel{display:flex;align-items:center;justify-content:space-between;gap:.7rem}.search-panel .search-field{flex:1;max-width:720px}.table-wrap td,.table-wrap th{padding:.75rem;font-size:.68rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--border-soft)}.table-wrap th{color:var(--text-muted);font-size:.57rem;text-transform:uppercase;letter-spacing:.06em}.table-wrap td strong,.table-wrap td small{display:block}.table-wrap td small{margin-top:.15rem;color:var(--text-subtle);font-size:.6rem}.empty{text-align:center;color:var(--text-muted);padding:1.5rem}.reason{margin:0;color:var(--text-muted);font-size:.66rem;line-height:1.5}.item-meta{display:grid;gap:.2rem}.item-meta span{display:grid;gap:.1rem;color:var(--text-muted);font-size:.6rem}.item-meta strong{color:var(--text-strong);font-size:.65rem}.empty-card{text-align:center;color:var(--text-muted)}@media(max-width:720px){.search-panel{align-items:stretch;flex-direction:column}.search-panel .search-field{max-width:none}.search-panel .soft-pill{align-self:flex-start}}
</style>
