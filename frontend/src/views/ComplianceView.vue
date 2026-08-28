<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, ExternalLink, Github, RefreshCw, ShieldAlert, Trash2 } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { GitHubConnection, ToolResult } from '../types/api'

interface ComplianceProbeData {
  full_name: string
  authenticated_login: string
  owned_by_connection: boolean
  status: string
  http_status: number | null
  accessible: boolean
  restricted: boolean
  fork: boolean | null
  private: boolean | null
  disabled: boolean | null
  html_url: string | null
  monitored_locally: boolean
  local_repository_id: string | null
  required_confirmation: string
}

const dialogs = useDialogStore()
const toasts = useToastStore()
const loading = ref(true)
const busy = ref('')
const connections = ref<GitHubConnection[]>([])
const selectedConnectionId = ref('')
const fullName = ref('')
const confirmation = ref('')
const localConfirmation = ref('')
const remoteDeleteBlocked = ref(false)
const probe = ref<ComplianceProbeData | null>(null)

const selectedConnection = computed(() => connections.value.find((item) => item.id === selectedConnectionId.value) || null)
const expectedOwner = computed(() => selectedConnection.value?.github_login || '')
const canDelete = computed(() => Boolean(probe.value && probe.value.owned_by_connection && confirmation.value === probe.value.required_confirmation && busy.value !== 'delete'))
const localCleanupExpected = computed(() => probe.value ? `REMOVER DO MONITOR ${probe.value.full_name}` : '')
const canLocalCleanup = computed(() => Boolean(probe.value?.monitored_locally && localConfirmation.value === localCleanupExpected.value && busy.value !== 'local-cleanup'))

function statusLabel(status: string): string {
  return ({ accessible: 'Acessível', legal_restriction: 'Restrição legal / DMCA', forbidden: 'Acesso administrativo negado', not_visible: 'Não visível pela API', unauthorized: 'Token não autorizado', error: 'Erro de diagnóstico' } as Record<string, string>)[status] || status
}
function statusTone(status: string): string {
  if (status === 'accessible') return 'success'
  if (status === 'legal_restriction') return 'danger'
  if (['forbidden', 'not_visible', 'unauthorized'].includes(status)) return 'warning'
  return 'muted'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await api.get<GitHubConnection[]>('/github/connections')
    connections.value = result.filter((item) => item.status !== 'demo')
    if (!selectedConnectionId.value && connections.value.length) selectedConnectionId.value = connections.value[0].id
  } catch (error) { toasts.error('Falha ao carregar conexões GitHub', error instanceof ApiError ? error.message : undefined) }
  finally { loading.value = false }
}

async function diagnose(): Promise<void> {
  if (!selectedConnection.value || !fullName.value.trim()) { toasts.warning('Informe a conexão e o repositório', 'Use o formato owner/repo.'); return }
  busy.value = 'probe'; probe.value = null; confirmation.value = ''; localConfirmation.value = ''; remoteDeleteBlocked.value = false
  try {
    const result = await api.post<ToolResult>(`/github-tools/connections/${selectedConnection.value.id}/compliance/probe`, { full_name: fullName.value.trim() })
    probe.value = result.data as unknown as ComplianceProbeData
    toasts.success('Diagnóstico concluído', result.message)
  } catch (error) { toasts.error('Diagnóstico recusado', error instanceof ApiError ? error.message : undefined) }
  finally { busy.value = '' }
}

async function deleteRepository(): Promise<void> {
  if (!selectedConnection.value || !probe.value || !canDelete.value) return
  const target = probe.value.full_name
  const sure = await dialogs.askConfirmation({
    title: 'Excluir definitivamente da conta GitHub?',
    message: `${target} será removido da sua conta GitHub. Esta operação não restaura nem contorna bloqueio DMCA; apenas solicita ao GitHub a exclusão da sua cópia/fork.`,
    tone: 'danger',
    confirmLabel: 'Excluir no GitHub',
  })
  if (!sure) return
  busy.value = 'delete'; remoteDeleteBlocked.value = false
  try {
    const result = await api.post<ToolResult>(`/github-tools/connections/${selectedConnection.value.id}/compliance/delete-repository`, { full_name: target, confirmation: confirmation.value })
    toasts.success('Repositório removido', result.message)
    probe.value = null; confirmation.value = ''; localConfirmation.value = ''; fullName.value = ''
  } catch (error) {
    if (error instanceof ApiError && error.status === 451) remoteDeleteBlocked.value = true
    toasts.error('O GitHub não permitiu a exclusão', error instanceof ApiError ? error.message : 'Verifique o token e o estado legal do repositório.')
  } finally { busy.value = '' }
}

async function removeLocalOnly(): Promise<void> {
  if (!selectedConnection.value || !probe.value || !canLocalCleanup.value) return
  const target = probe.value.full_name
  const sure = await dialogs.askConfirmation({
    title: 'Remover somente do Git Monitor?',
    message: `${target} será removido apenas do monitoramento local. O repositório continuará existindo na sua conta GitHub enquanto a plataforma mantiver a restrição legal.`,
    tone: 'warning',
    confirmLabel: 'Remover do monitor',
  })
  if (!sure) return
  busy.value = 'local-cleanup'
  try {
    const result = await api.post<ToolResult>(`/github-tools/connections/${selectedConnection.value.id}/compliance/remove-local`, { full_name: target, confirmation: localConfirmation.value })
    toasts.success('Removido do Git Monitor', result.message)
    if (probe.value) probe.value = { ...probe.value, monitored_locally: false, local_repository_id: null }
    localConfirmation.value = ''
  } catch (error) { toasts.error('Falha na limpeza local', error instanceof ApiError ? error.message : undefined) }
  finally { busy.value = '' }
}

onMounted(load)
</script>

<template>
  <div class="page-stack compliance-page">
    <section class="page-heading"><div><span class="eyebrow">CONFORMIDADE E LIMPEZA</span><h2>Repositório bloqueado / DMCA</h2><p>Remova da sua própria conta GitHub uma cópia ou fork que ficou indisponível por restrição legal, mesmo quando ele não aparece mais no catálogo do Git Monitor.</p></div><button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16" />Atualizar conexões</button></section>
    <section class="notice-card"><ShieldAlert :size="22" /><div><strong>Esta ferramenta não contorna um bloqueio legal.</strong><p>Ela chama somente a API oficial do GitHub. Se o GitHub devolver HTTP 451 ao DELETE, a remoção remota é impossível pela API. Nesse caso você pode retirar o registro do Git Monitor e tratar a exclusão da conta diretamente com o GitHub.</p></div></section>
    <section class="compliance-grid">
      <article class="tool-card"><header><Github :size="19" /><div><strong>1. Identificar a cópia</strong><span>Não precisa estar sendo monitorada</span></div></header><label class="field"><span>Conexão GitHub</span><select v-model="selectedConnectionId" :disabled="loading"><option v-for="connection in connections" :key="connection.id" :value="connection.id">{{ connection.name }} · @{{ connection.github_login }}</option></select></label><label class="field"><span>Repositório completo</span><input v-model="fullName" :placeholder="expectedOwner ? `${expectedOwner}/nome-do-fork` : 'owner/repo'" @keyup.enter="diagnose" /></label><small v-if="expectedOwner" class="field-help">Por segurança, esta operação aceita apenas repositórios cujo owner seja <strong>@{{ expectedOwner }}</strong>.</small><button class="button primary" :disabled="busy==='probe' || !selectedConnectionId || !fullName.trim()" @click="diagnose"><ShieldAlert :size="15" />Diagnosticar</button></article>
      <article class="tool-card danger-zone"><header><Trash2 :size="19" /><div><strong>2. Exclusão definitiva</strong><span>Confirmação forte por owner/repo</span></div></header><template v-if="probe"><div :class="['probe-status', statusTone(probe.status)]"><component :is="probe.status === 'accessible' ? CheckCircle2 : AlertTriangle" :size="18" /><div><strong>{{ statusLabel(probe.status) }}</strong><span>HTTP {{ probe.http_status ?? '—' }} · {{ probe.full_name }}</span></div></div><dl class="probe-details"><div><dt>Fork</dt><dd>{{ probe.fork === null ? 'não observável' : probe.fork ? 'sim' : 'não' }}</dd></div><div><dt>Privado</dt><dd>{{ probe.private === null ? 'não observável' : probe.private ? 'sim' : 'não' }}</dd></div><div><dt>Disabled</dt><dd>{{ probe.disabled === null ? 'não observável' : probe.disabled ? 'sim' : 'não' }}</dd></div><div><dt>No Git Monitor</dt><dd>{{ probe.monitored_locally ? 'sim' : 'não' }}</dd></div></dl><label class="field confirmation"><span>Digite exatamente</span><code>{{ probe.required_confirmation }}</code><input v-model="confirmation" autocomplete="off" /></label><button class="button danger" :disabled="!canDelete" @click="deleteRepository"><Trash2 :size="15" />Excluir definitivamente da conta GitHub</button><section v-if="remoteDeleteBlocked || probe.http_status === 451" class="blocked-actions"><div class="blocked-copy"><AlertTriangle :size="18" /><div><strong>Exclusão remota bloqueada pelo GitHub</strong><p>HTTP 451 significa que o GitHub recusou também o DELETE. O Git Monitor não pode forçar essa operação no servidor do GitHub.</p></div></div><a class="button secondary" href="https://support.github.com/contact" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15" />Abrir suporte do GitHub</a><template v-if="probe.monitored_locally"><label class="field confirmation local-confirmation"><span>Para limpar somente o Git Monitor, digite exatamente</span><code>{{ localCleanupExpected }}</code><input v-model="localConfirmation" autocomplete="off" /></label><button class="button secondary danger-text" :disabled="!canLocalCleanup" @click="removeLocalOnly"><Trash2 :size="15" />Remover somente do Git Monitor</button></template><p v-else class="local-clean">O repositório já não está cadastrado localmente no Git Monitor.</p></section></template><div v-else class="waiting-state"><AlertTriangle :size="22" /><strong>Faça o diagnóstico primeiro</strong><p>A exclusão só é habilitada após validar a conta e gerar a frase de confirmação.</p></div></article>
    </section>
  </div>
</template>

<style scoped>
.notice-card{display:flex;gap:.8rem;align-items:flex-start;padding:1rem;border:1px solid color-mix(in srgb,var(--warning) 35%,var(--border));border-radius:1rem;background:color-mix(in srgb,var(--warning) 7%,var(--surface));color:var(--warning)}.notice-card strong{color:var(--text-strong)}.notice-card p{margin:.2rem 0 0;color:var(--text-muted);font-size:.72rem;line-height:1.55}.compliance-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem}.tool-card{display:grid;align-content:start;gap:.85rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.tool-card header{display:flex;gap:.65rem;align-items:center;padding-bottom:.75rem;border-bottom:1px solid var(--border-soft);color:var(--primary-strong)}.tool-card header>div{display:grid}.tool-card header strong{color:var(--text-strong)}.tool-card header span{color:var(--text-muted);font-size:.62rem}.field{display:grid;gap:.35rem}.field>span{color:var(--text-muted);font-size:.65rem;font-weight:700}.field input,.field select{width:100%;min-height:2.6rem;padding:.55rem .7rem;border:1px solid var(--border);border-radius:.65rem;background:var(--surface-raised);color:var(--text-strong)}.field-help{color:var(--text-muted);line-height:1.45}.probe-status{display:flex;gap:.6rem;align-items:center;padding:.75rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface-raised)}.probe-status>div{display:grid}.probe-status span{font-size:.62rem;color:var(--text-muted)}.probe-status.success{color:var(--success)}.probe-status.warning{color:var(--warning)}.probe-status.danger{color:var(--danger)}.probe-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem;margin:0}.probe-details>div{padding:.55rem;border:1px solid var(--border-soft);border-radius:.65rem;background:var(--surface-soft)}.probe-details dt{color:var(--text-muted);font-size:.58rem}.probe-details dd{margin:.15rem 0 0;color:var(--text-strong);font-weight:700}.confirmation code{display:block;padding:.55rem;border-radius:.55rem;background:var(--surface-soft);color:var(--danger);font-size:.72rem}.waiting-state{display:grid;place-items:center;gap:.35rem;min-height:13rem;text-align:center;color:var(--text-muted)}.waiting-state strong{color:var(--text-strong)}.waiting-state p{max-width:34rem;margin:0;font-size:.7rem}.button.danger{color:#fff;border-color:var(--danger);background:var(--danger)}.blocked-actions{display:grid;gap:.75rem;padding:.8rem;border:1px solid color-mix(in srgb,var(--danger) 30%,var(--border));border-radius:.8rem;background:color-mix(in srgb,var(--danger) 5%,var(--surface))}.blocked-copy{display:flex;gap:.6rem;color:var(--danger)}.blocked-copy>div{display:grid}.blocked-copy strong{color:var(--text-strong)}.blocked-copy p,.local-clean{margin:.2rem 0 0;color:var(--text-muted);font-size:.68rem;line-height:1.5}.blocked-actions .button{justify-self:start}.local-confirmation{margin-top:.25rem}@media(max-width:900px){.compliance-grid{grid-template-columns:1fr}.probe-details{grid-template-columns:1fr 1fr}}@media(max-width:520px){.probe-details{grid-template-columns:1fr}.blocked-actions .button{width:100%}}
</style>
