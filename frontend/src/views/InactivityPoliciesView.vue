<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Activity, AlertTriangle, CheckCircle2, Clock3, Edit3, Eye, LockKeyhole, Plus,
  RefreshCw, Save, Search, ShieldAlert, Trash2, X
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { formatDateTime, formatRelative } from '../services/format'
import { useToastStore } from '../stores/toast'
import type {
  InactivityActionLog, InactivityEvaluationResult, InactivityPolicy, PaginatedResponse, Repository
} from '../types/api'

const toasts = useToastStore()
const policies = ref<InactivityPolicy[]>([])
const repositories = ref<Repository[]>([])
const logs = ref<InactivityActionLog[]>([])
const loading = ref(true)
const saving = ref(false)
const evaluating = ref('')
const showForm = ref(false)
const editingId = ref<string | null>(null)
const repositorySearch = ref('')

const sourceOptions = [
  { value: 'push', label: 'Pushes' },
  { value: 'commit', label: 'Commits' },
  { value: 'pull_request', label: 'Pull Requests' },
  { value: 'issue', label: 'Issues e comentários' },
  { value: 'actions', label: 'GitHub Actions' },
  { value: 'release', label: 'Releases' },
  { value: 'repository_event', label: 'Eventos do repositório' },
  { value: 'repository_metadata', label: 'Metadados/configuração' }
]
const defaultSources = sourceOptions.map((item) => item.value)
const form = reactive({
  name: '', description: '', timeout_value: 30, timeout_unit: 'days', action: 'private',
  enabled: true, activity_sources: [...defaultSources], repository_ids: [] as string[]
})

const filteredRepositories = computed(() => {
  const query = repositorySearch.value.trim().toLowerCase()
  if (!query) return repositories.value
  return repositories.value.filter((item) =>
    item.full_name.toLowerCase().includes(query) || (item.description || '').toLowerCase().includes(query)
  )
})

function resetForm(): void {
  editingId.value = null
  Object.assign(form, {
    name: '', description: '', timeout_value: 30, timeout_unit: 'days', action: 'private',
    enabled: true, activity_sources: [...defaultSources], repository_ids: []
  })
  repositorySearch.value = ''
}

function beginCreate(): void { resetForm(); showForm.value = true }
function beginEdit(policy: InactivityPolicy): void {
  editingId.value = policy.id
  Object.assign(form, {
    name: policy.name,
    description: policy.description || '',
    timeout_value: policy.timeout_value,
    timeout_unit: policy.timeout_unit,
    action: policy.action,
    enabled: policy.enabled,
    activity_sources: [...policy.activity_sources],
    repository_ids: [...policy.repository_ids]
  })
  showForm.value = true
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function closeForm(): void { showForm.value = false; resetForm() }

async function loadRepositories(): Promise<Repository[]> {
  const all: Repository[] = []
  let page = 1
  let pages = 1
  do {
    const response = await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100`)
    all.push(...response.items)
    pages = response.pages
    page += 1
  } while (page <= pages)
  return all
}

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    const [loadedPolicies, loadedRepositories, loadedLogs] = await Promise.all([
      api.get<InactivityPolicy[]>('/inactivity-policies'),
      loadRepositories(),
      api.get<InactivityActionLog[]>('/inactivity-policies/logs?limit=100')
    ])
    policies.value = loadedPolicies
    repositories.value = loadedRepositories
    logs.value = loadedLogs
  } catch (error) {
    toasts.error('Falha ao carregar automações', error instanceof ApiError ? error.message : undefined)
  } finally { loading.value = false }
}

function toggleRepository(id: string): void {
  const index = form.repository_ids.indexOf(id)
  if (index >= 0) form.repository_ids.splice(index, 1)
  else form.repository_ids.push(id)
}
function selectFiltered(): void {
  const selected = new Set(form.repository_ids)
  filteredRepositories.value.forEach((item) => selected.add(item.id))
  form.repository_ids = [...selected]
}
function clearRepositories(): void { form.repository_ids = [] }
function toggleSource(source: string): void {
  const index = form.activity_sources.indexOf(source)
  if (index >= 0) form.activity_sources.splice(index, 1)
  else form.activity_sources.push(source)
}

async function savePolicy(): Promise<void> {
  if (!form.name.trim()) { toasts.warning('Informe um nome para a lista'); return }
  if (!form.activity_sources.length) { toasts.warning('Selecione ao menos uma fonte de atividade'); return }
  if (!form.repository_ids.length) { toasts.warning('Selecione ao menos um repositório'); return }
  if (form.action === 'private' && form.enabled) {
    const ok = window.confirm(
      `Esta política poderá tornar ${form.repository_ids.length} repositório(s) PRIVADO(S) automaticamente após o timeout. Deseja salvar?`
    )
    if (!ok) return
  }
  saving.value = true
  const payload = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    timeout_value: Number(form.timeout_value),
    timeout_unit: form.timeout_unit,
    action: form.action,
    enabled: form.enabled,
    activity_sources: form.activity_sources,
    repository_ids: form.repository_ids
  }
  try {
    if (editingId.value) await api.put<InactivityPolicy>(`/inactivity-policies/${editingId.value}`, payload)
    else await api.post<InactivityPolicy>('/inactivity-policies', payload)
    toasts.success('Política salva', 'O monitor periódico avaliará somente os repositórios marcados.')
    closeForm()
    await load(true)
  } catch (error) {
    toasts.error('Não foi possível salvar', error instanceof ApiError ? error.message : undefined)
  } finally { saving.value = false }
}

async function deletePolicy(policy: InactivityPolicy): Promise<void> {
  if (!window.confirm(`Excluir a política “${policy.name}”? Isso não altera a visibilidade atual dos repositórios.`)) return
  try {
    await api.delete(`/inactivity-policies/${policy.id}`)
    toasts.success('Política removida')
    await load(true)
  } catch (error) { toasts.error('Falha ao remover', error instanceof ApiError ? error.message : undefined) }
}

function evaluationMessage(result: InactivityEvaluationResult): string {
  return `${result.due} vencido(s), ${result.privatized} privado(s), ${result.notified} alerta(s), ${result.failed} falha(s).`
}

async function evaluatePolicy(policy: InactivityPolicy): Promise<void> {
  if (policy.action === 'private' && !window.confirm(`Executar agora “${policy.name}”? Repositórios vencidos poderão ser privados imediatamente.`)) return
  evaluating.value = policy.id
  try {
    const result = await api.post<InactivityEvaluationResult>(`/inactivity-policies/${policy.id}/evaluate`)
    toasts.success('Avaliação concluída', evaluationMessage(result))
    await load(true)
  } catch (error) { toasts.error('Falha na avaliação', error instanceof ApiError ? error.message : undefined) }
  finally { evaluating.value = '' }
}

async function evaluateAll(): Promise<void> {
  if (!window.confirm('Avaliar todas as políticas ativas agora? Políticas de privacidade podem alterar repositórios vencidos.')) return
  evaluating.value = 'all'
  try {
    const result = await api.post<InactivityEvaluationResult>('/inactivity-policies/evaluate-all')
    toasts.success('Avaliação geral concluída', evaluationMessage(result))
    await load(true)
  } catch (error) { toasts.error('Falha na avaliação geral', error instanceof ApiError ? error.message : undefined) }
  finally { evaluating.value = '' }
}

function unitLabel(unit: string, value: number): string {
  const labels: Record<string, [string, string]> = {
    hours: ['hora', 'horas'], days: ['dia', 'dias'], weeks: ['semana', 'semanas'], months: ['mês', 'meses']
  }
  const pair = labels[unit] || [unit, unit]
  return value === 1 ? pair[0] : pair[1]
}
function sourceLabel(source: string): string { return sourceOptions.find((item) => item.value === source)?.label || source }
function repoById(id: string): Repository | undefined { return repositories.value.find((item) => item.id === id) }

function timeoutMs(policy: InactivityPolicy): number {
  const unit = { hours: 3600e3, days: 86400e3, weeks: 604800e3, months: 2592000e3 }[policy.timeout_unit]
  return policy.timeout_value * unit
}
function dueState(repository: Repository | undefined, policy: InactivityPolicy): { label: string; due: boolean } {
  if (!repository?.last_activity_at || !repository.activity_observed_at) return { label: 'Aguardando leitura completa', due: false }
  const deadline = new Date(repository.last_activity_at).getTime() + timeoutMs(policy)
  const diff = deadline - Date.now()
  if (diff <= 0) return { label: `Timeout vencido ${formatRelative(new Date(deadline).toISOString())}`, due: true }
  const days = Math.ceil(diff / 86400e3)
  return { label: `vence em ~${days} dia(s)`, due: false }
}

onMounted(load)
</script>

<template>
  <div class="page-stack inactivity-page">
    <section class="page-heading">
      <div><span class="eyebrow">AUTOMAÇÃO DE GOVERNANÇA</span><h2>Monitoramento por inatividade</h2><p>Crie listas independentes com timeouts diferentes. Qualquer atividade selecionada reinicia o relógio do repositório.</p></div>
      <div class="heading-actions"><button class="button secondary" :disabled="evaluating==='all'" @click="evaluateAll"><RefreshCw :size="16" />Avaliar agora</button><button class="button primary" @click="beginCreate"><Plus :size="16" />Nova lista</button></div>
    </section>

    <section class="explain-card">
      <Activity :size="21" />
      <div><strong>O que conta como atividade?</strong><p>Push, commit, atualização de PR, issue/comentário, GitHub Actions, release, eventos e alterações de metadados — conforme as fontes marcadas em cada política. O sistema usa a atividade mais recente entre elas. Sem uma leitura completa, nenhuma ação automática é executada.</p></div>
    </section>

    <section v-if="showForm" class="policy-editor">
      <header><div><span class="eyebrow">{{ editingId ? 'EDITAR LISTA' : 'NOVA LISTA' }}</span><h3>{{ editingId ? 'Atualizar política' : 'Criar política de inatividade' }}</h3></div><button class="icon-button" @click="closeForm"><X :size="17" /></button></header>
      <div class="editor-grid"><label class="field"><span>Nome da lista</span><input v-model="form.name" placeholder="Ex.: Projetos temporários 30 dias" /></label><label class="field"><span>Descrição</span><input v-model="form.description" placeholder="Objetivo desta política" /></label><label class="field"><span>Timeout</span><input v-model.number="form.timeout_value" type="number" min="1" max="3650" /></label><label class="field"><span>Unidade</span><select v-model="form.timeout_unit"><option value="hours">Horas</option><option value="days">Dias</option><option value="weeks">Semanas</option><option value="months">Meses (30 dias)</option></select></label><label class="field"><span>Ação</span><select v-model="form.action"><option value="private">Privar automaticamente</option><option value="notify">Somente alertar</option></select></label><label class="switch-field"><input v-model="form.enabled" type="checkbox" /><span><strong>Política ativa</strong><small>O Celery Beat avalia a cada 15 minutos.</small></span></label></div>

      <div class="sources"><strong>Movimentos que reiniciam o timeout</strong><div><label v-for="source in sourceOptions" :key="source.value" :class="{ active: form.activity_sources.includes(source.value) }"><input type="checkbox" :checked="form.activity_sources.includes(source.value)" @change="toggleSource(source.value)" />{{ source.label }}</label></div></div>

      <div class="repository-selector"><header><div><strong>Repositórios desta lista</strong><span>{{ form.repository_ids.length }} selecionado(s)</span></div><div class="selector-actions"><button class="button ghost compact" @click="selectFiltered">Selecionar filtrados</button><button class="button ghost compact" @click="clearRepositories">Limpar</button></div></header><label class="repo-search"><Search :size="16" /><input v-model="repositorySearch" placeholder="Buscar owner/repo…" /></label><div class="repository-list"><label v-for="repository in filteredRepositories" :key="repository.id" :class="{ selected: form.repository_ids.includes(repository.id) }"><input type="checkbox" :checked="form.repository_ids.includes(repository.id)" @change="toggleRepository(repository.id)" /><div><strong>{{ repository.full_name }}</strong><span>{{ repository.private ? 'Privado' : 'Público' }} · última atividade {{ formatRelative(repository.last_activity_at) }}</span></div><LockKeyhole v-if="repository.private" :size="15" /><Eye v-else :size="15" /></label></div></div>
      <div class="editor-footer"><p v-if="form.action==='private'"><ShieldAlert :size="16" />A alteração de visibilidade exige permissão <strong>Administration: write</strong> no token GitHub.</p><button class="button primary" :disabled="saving" @click="savePolicy"><Save :size="16" />{{ saving ? 'Salvando…' : 'Salvar política' }}</button></div>
    </section>

    <div v-if="loading" class="policy-grid"><div v-for="n in 3" :key="n" class="skeleton policy-skeleton" /></div>
    <section v-else-if="!policies.length" class="empty-policy"><Clock3 :size="30" /><strong>Nenhuma política configurada</strong><p>Crie uma lista, escolha os repositórios e defina o timeout.</p><button class="button primary" @click="beginCreate"><Plus :size="16" />Criar primeira lista</button></section>
    <section v-else class="policy-grid">
      <article v-for="policy in policies" :key="policy.id" class="policy-card" :class="{ disabled: !policy.enabled }">
        <header><div class="policy-icon" :class="policy.action"><LockKeyhole v-if="policy.action==='private'" :size="20" /><AlertTriangle v-else :size="20" /></div><div><strong>{{ policy.name }}</strong><span>{{ policy.description || 'Sem descrição' }}</span></div><em :class="policy.enabled ? 'enabled' : ''">{{ policy.enabled ? 'Ativa' : 'Pausada' }}</em></header>
        <div class="policy-metrics"><div><strong>{{ policy.timeout_value }}</strong><span>{{ unitLabel(policy.timeout_unit, policy.timeout_value) }}</span></div><div><strong>{{ policy.repository_count }}</strong><span>repositórios</span></div><div><strong>{{ policy.activity_sources.length }}</strong><span>fontes</span></div></div>
        <div class="policy-source-list"><span v-for="source in policy.activity_sources" :key="source">{{ sourceLabel(source) }}</span></div>
        <div class="policy-repositories"><article v-for="id in policy.repository_ids.slice(0,8)" :key="id"><div><strong>{{ repoById(id)?.full_name || id }}</strong><span>{{ repoById(id)?.last_activity_summary || 'Aguardando atividade observada' }}</span></div><div class="due" :class="{ expired: dueState(repoById(id), policy).due }">{{ dueState(repoById(id), policy).label }}</div></article><small v-if="policy.repository_count>8">+ {{ policy.repository_count-8 }} repositório(s)</small></div>
        <footer><span>Última avaliação: {{ formatDateTime(policy.last_evaluated_at) }}</span><div><button class="button ghost compact" @click="beginEdit(policy)"><Edit3 :size="14" />Editar</button><button class="button secondary compact" :disabled="evaluating===policy.id" @click="evaluatePolicy(policy)"><RefreshCw :size="14" />Avaliar</button><button class="button ghost compact danger-text" @click="deletePolicy(policy)"><Trash2 :size="14" />Excluir</button></div></footer>
      </article>
    </section>

    <section class="history-card"><header><div><span class="eyebrow">HISTÓRICO</span><h3>Ações automáticas</h3></div><span>{{ logs.length }} evento(s)</span></header><div v-if="!logs.length" class="history-empty">Nenhuma ação automática executada.</div><div v-else class="history-list"><article v-for="log in logs" :key="log.id"><div class="history-status" :class="log.status"><CheckCircle2 v-if="log.status==='success'" :size="17" /><AlertTriangle v-else :size="17" /></div><div><strong>{{ log.repository_full_name }}</strong><span>{{ log.action==='private' ? 'Privado automaticamente' : 'Alerta de inatividade' }} · {{ log.reason }}</span><small>{{ formatDateTime(log.created_at) }}</small></div></article></div></section>
  </div>
</template>

<style scoped>
.heading-actions{display:flex;gap:.55rem}.explain-card{display:flex;align-items:flex-start;gap:.8rem;padding:1rem;color:var(--primary-strong);border:1px solid color-mix(in srgb,var(--primary) 24%,var(--border));border-radius:1rem;background:color-mix(in srgb,var(--primary) 5%,var(--surface))}.explain-card strong{color:var(--text-strong)}.explain-card p{margin:.2rem 0 0;color:var(--text-muted);font-size:.74rem;line-height:1.5}.policy-editor,.history-card{display:grid;gap:1rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.policy-editor>header,.history-card>header,.repository-selector>header{display:flex;align-items:center;justify-content:space-between;gap:1rem}.policy-editor h3,.history-card h3{margin:.1rem 0;color:var(--text-strong)}.editor-grid{display:grid;grid-template-columns:2fr 2fr .7fr .9fr 1.3fr 1.2fr;gap:.7rem;align-items:end}.switch-field{display:flex;align-items:center;gap:.55rem;min-height:2.7rem;color:var(--text)}.switch-field span{display:grid}.switch-field small{color:var(--text-muted);font-size:.58rem}.sources{display:grid;gap:.55rem;padding:.8rem;border:1px solid var(--border-soft);border-radius:.8rem;background:var(--surface-soft)}.sources>strong{color:var(--text-strong);font-size:.75rem}.sources>div{display:flex;flex-wrap:wrap;gap:.4rem}.sources label{display:flex;align-items:center;gap:.35rem;padding:.4rem .55rem;color:var(--text-muted);font-size:.65rem;border:1px solid var(--border);border-radius:999px;background:var(--surface);cursor:pointer}.sources label.active{color:var(--primary-strong);border-color:color-mix(in srgb,var(--primary) 45%,var(--border));background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.repository-selector{display:grid;gap:.65rem}.repository-selector header span{display:block;color:var(--text-muted);font-size:.65rem}.selector-actions{display:flex;gap:.4rem}.repo-search{display:flex;align-items:center;gap:.5rem;padding:0 .7rem;min-height:2.5rem;border:1px solid var(--border);border-radius:.7rem;background:var(--surface-raised)}.repo-search input{width:100%;border:0;outline:0;background:transparent;color:var(--text)}.repository-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem;max-height:360px;overflow:auto;padding:.2rem}.repository-list label{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.55rem;padding:.65rem;border:1px solid var(--border);border-radius:.72rem;background:var(--surface-raised);cursor:pointer}.repository-list label.selected{border-color:color-mix(in srgb,var(--primary) 48%,var(--border));background:color-mix(in srgb,var(--primary) 6%,var(--surface))}.repository-list label div{display:grid;min-width:0}.repository-list strong{overflow:hidden;color:var(--text-strong);font-size:.72rem;text-overflow:ellipsis;white-space:nowrap}.repository-list span{color:var(--text-muted);font-size:.58rem}.editor-footer{display:flex;justify-content:space-between;align-items:center;gap:1rem}.editor-footer p{display:flex;align-items:center;gap:.4rem;margin:0;color:var(--warning);font-size:.68rem}.policy-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.policy-skeleton{height:330px;border-radius:1rem}.policy-card{display:grid;gap:.85rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.policy-card.disabled{opacity:.65}.policy-card>header{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem}.policy-icon{display:grid;place-items:center;width:2.7rem;height:2.7rem;border-radius:.8rem;color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,var(--surface))}.policy-icon.private{color:var(--danger);background:color-mix(in srgb,var(--danger) 8%,var(--surface))}.policy-card header>div:nth-child(2){display:grid}.policy-card header strong{color:var(--text-strong)}.policy-card header span{color:var(--text-muted);font-size:.65rem}.policy-card header em{padding:.2rem .45rem;color:var(--text-muted);font-size:.58rem;font-style:normal;border-radius:999px;background:var(--surface-soft)}.policy-card header em.enabled{color:var(--success);background:color-mix(in srgb,var(--success) 10%,var(--surface))}.policy-metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:.45rem}.policy-metrics div{display:grid;padding:.65rem;border:1px solid var(--border-soft);border-radius:.7rem;background:var(--surface-soft)}.policy-metrics strong{color:var(--text-strong);font-size:1rem}.policy-metrics span{color:var(--text-muted);font-size:.58rem}.policy-source-list{display:flex;flex-wrap:wrap;gap:.3rem}.policy-source-list span{padding:.18rem .38rem;color:var(--text-muted);font-size:.55rem;border-radius:999px;background:var(--surface-soft)}.policy-repositories{display:grid;border:1px solid var(--border-soft);border-radius:.75rem;overflow:hidden}.policy-repositories article{display:flex;align-items:center;justify-content:space-between;gap:.7rem;padding:.55rem .65rem;border-bottom:1px solid var(--border-soft)}.policy-repositories article:last-of-type{border-bottom:0}.policy-repositories article>div:first-child{display:grid;min-width:0}.policy-repositories strong{overflow:hidden;color:var(--text-strong);font-size:.65rem;text-overflow:ellipsis;white-space:nowrap}.policy-repositories span{overflow:hidden;color:var(--text-muted);font-size:.55rem;text-overflow:ellipsis;white-space:nowrap}.policy-repositories>small{padding:.45rem;color:var(--text-muted)}.due{flex:0 0 auto;color:var(--text-muted);font-size:.58rem}.due.expired{color:var(--danger);font-weight:800}.policy-card>footer{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding-top:.6rem;border-top:1px solid var(--border-soft)}.policy-card>footer>span{color:var(--text-subtle);font-size:.58rem}.policy-card>footer>div{display:flex;gap:.35rem}.empty-policy{display:grid;place-items:center;gap:.45rem;padding:4rem 1rem;color:var(--text-muted);text-align:center;border:1px dashed var(--border);border-radius:1rem;background:var(--surface)}.empty-policy strong{color:var(--text-strong)}.empty-policy p{margin:0}.history-list{display:grid}.history-list article{display:grid;grid-template-columns:auto 1fr;gap:.65rem;padding:.65rem 0;border-bottom:1px solid var(--border-soft)}.history-list article:last-child{border-bottom:0}.history-status{display:grid;place-items:center;width:2rem;height:2rem;border-radius:.6rem;color:var(--success);background:color-mix(in srgb,var(--success) 9%,var(--surface))}.history-status.failed{color:var(--danger);background:color-mix(in srgb,var(--danger) 8%,var(--surface))}.history-list article>div:last-child{display:grid}.history-list strong{color:var(--text-strong);font-size:.72rem}.history-list span{color:var(--text-muted);font-size:.62rem}.history-list small,.history-empty{color:var(--text-subtle);font-size:.58rem}.danger-text{color:var(--danger)!important}
@media(max-width:1200px){.editor-grid{grid-template-columns:repeat(3,1fr)}.repository-list{grid-template-columns:repeat(2,1fr)}}@media(max-width:850px){.policy-grid{grid-template-columns:1fr}.repository-list{grid-template-columns:1fr}.editor-grid{grid-template-columns:1fr 1fr}}@media(max-width:600px){.heading-actions,.editor-footer,.policy-card>footer{align-items:stretch;flex-direction:column}.heading-actions .button,.editor-footer .button,.policy-card>footer .button{width:100%}.editor-grid{grid-template-columns:1fr}.selector-actions{display:grid;grid-template-columns:1fr 1fr}.policy-card>footer>div{display:grid;grid-template-columns:1fr 1fr}.policy-card>footer>div .button:last-child{grid-column:1/-1}.policy-repositories article{align-items:flex-start;flex-direction:column}.due{align-self:flex-end}}
</style>
