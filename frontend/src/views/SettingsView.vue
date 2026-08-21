<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle, BellRing, CheckCircle2, ChevronDown, ChevronUp, Copy, Database, Download,
  Eye, EyeOff, Github, KeyRound, Link2, ListChecks, LockKeyhole, Moon, Plus, RefreshCw,
  Save, Search, ShieldCheck, Smartphone, Sun, Trash2, Webhook
} from 'lucide-vue-next'
import StatusBadge from '../components/StatusBadge.vue'
import { usePwaInstall } from '../composables/usePwaInstall'
import { ApiError, api } from '../services/api'
import { formatDateTime } from '../services/format'
import { useAuthStore } from '../stores/auth'
import { useThemeStore, type ThemePreference } from '../stores/theme'
import { useToastStore } from '../stores/toast'
import type {
  GitHubConnection, MessageResponse, RemoteRepository, RepositoryImportResponse, SessionItem,
  SyncResponse, TwoFactorSetup, TwoFactorStatus, WebhookConfigureResult
} from '../types/api'

const auth = useAuthStore()
const appVersion = String(import.meta.env.VITE_APP_VERSION || '0.3.0')
const theme = useThemeStore()
const toasts = useToastStore()
const route = useRoute()
const router = useRouter()
const { canInstall, isStandalone, install } = usePwaInstall()

const loading = ref(true)
const connections = ref<GitHubConnection[]>([])
const sessions = ref<SessionItem[]>([])
const twoFactor = ref<TwoFactorStatus>({ enabled: false, confirmed_at: null, recovery_codes_remaining: 0 })
const twoFactorSetup = ref<TwoFactorSetup | null>(null)
const twoFactorCode = ref('')
const twoFactorPassword = ref('')
const showConnectionForm = ref(false)
const showToken = ref(false)
const savingConnection = ref(false)
const activeConnectionId = ref<string | null>(null)
const remoteLoadingId = ref<string | null>(null)
const remoteQuery = reactive<Record<string, string>>({})
const remoteRepositories = reactive<Record<string, RemoteRepository[]>>({})
const importingId = ref<string | null>(null)
const connectionForm = reactive({ name: 'GitHub principal', token: '', auto_import: true, api_url: 'https://api.github.com' })
const passwordForm = reactive({ current: '', next: '', confirmation: '' })
const changingPassword = ref(false)
const browserPermission = ref<'default' | 'denied' | 'granted' | 'unsupported'>('Notification' in window ? Notification.permission : 'unsupported')
const mustChangePassword = computed(() => auth.user?.must_change_password || route.query.password === 'required')
const realConnections = computed(() => connections.value.filter((item) => item.status !== 'demo'))

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    const [loadedConnections, loaded2fa, loadedSessions] = await Promise.all([
      api.get<GitHubConnection[]>('/github/connections'),
      api.get<TwoFactorStatus>('/auth/2fa/status'),
      api.get<SessionItem[]>('/auth/sessions')
    ])
    connections.value = loadedConnections
    twoFactor.value = loaded2fa
    sessions.value = loadedSessions
    if (!realConnections.value.length) showConnectionForm.value = true
  } catch (error) {
    toasts.error('Falha ao carregar configurações', error instanceof ApiError ? error.message : undefined)
  } finally { loading.value = false }
}

async function createConnection(): Promise<void> {
  if (!connectionForm.token.trim()) return
  savingConnection.value = true
  try {
    const created = await api.post<GitHubConnection>('/github/connections', {
      name: connectionForm.name.trim(), token: connectionForm.token.trim(), auto_import: connectionForm.auto_import, api_url: connectionForm.api_url.trim()
    })
    connectionForm.token = ''
    showConnectionForm.value = false
    toasts.success('GitHub conectado', `${created.available_repository_count || created.repository_count} repositório(s) acessíveis; o catálogo já está sendo preparado.`)
    await loadAll()
    await router.push('/repositories')
  } catch (error) { toasts.error('Não foi possível conectar', error instanceof ApiError ? error.message : undefined) }
  finally { savingConnection.value = false }
}

async function syncConnection(connection: GitHubConnection): Promise<void> {
  try {
    const result = await api.post<SyncResponse>(`/github/connections/${connection.id}/sync`)
    toasts.success('Catálogo atualizado', `${result.message} Acompanhe o detalhamento na Fila.`)
    await loadAll()
  } catch (error) { toasts.error('Falha ao sincronizar', error instanceof ApiError ? error.message : undefined) }
}

async function removeConnection(connection: GitHubConnection): Promise<void> {
  if (!window.confirm(`Remover a conexão “${connection.name}” e os dados locais monitorados? Os repositórios do GitHub não serão excluídos.`)) return
  try {
    const result = await api.delete<MessageResponse>(`/github/connections/${connection.id}`)
    toasts.success('Conexão removida', result.message)
    delete remoteRepositories[connection.id]
    await loadAll()
  } catch (error) { toasts.error('Não foi possível remover', error instanceof ApiError ? error.message : undefined) }
}

async function toggleRemote(connection: GitHubConnection): Promise<void> {
  if (activeConnectionId.value === connection.id) { activeConnectionId.value = null; return }
  activeConnectionId.value = connection.id
  if (remoteRepositories[connection.id]) return
  remoteLoadingId.value = connection.id
  try {
    remoteRepositories[connection.id] = await api.get<RemoteRepository[]>(`/github/connections/${connection.id}/remote-repositories`)
  } catch (error) { toasts.error('Falha ao consultar o GitHub', error instanceof ApiError ? error.message : undefined) }
  finally { remoteLoadingId.value = null }
}

function filteredRemote(connectionId: string): RemoteRepository[] {
  const term = (remoteQuery[connectionId] || '').trim().toLowerCase()
  const items = remoteRepositories[connectionId] || []
  return term ? items.filter((item) => item.full_name.toLowerCase().includes(term) || (item.language || '').toLowerCase().includes(term)) : items
}
function selectedRemote(connectionId: string): number[] { return (remoteRepositories[connectionId] || []).filter((item) => item.selected).map((item) => item.github_id) }
function selectAllRemote(connectionId: string, selected: boolean): void { for (const item of filteredRemote(connectionId)) item.selected = selected }

async function monitorSelected(connection: GitHubConnection, all = false): Promise<void> {
  const source = remoteRepositories[connection.id] || []
  const ids = all ? source.map((item) => item.github_id) : selectedRemote(connection.id)
  if (!ids.length) { toasts.info('Selecione projetos', 'Marque ao menos um repositório para monitorar.'); return }
  importingId.value = connection.id
  try {
    const result = await api.post<RepositoryImportResponse>(`/github/connections/${connection.id}/import`, { repository_ids: ids })
    toasts.success('Monitoramento atualizado', `${result.imported_count} novo(s), ${result.already_monitored_count} já monitorado(s). ${result.queued_count} job(s) na fila.`)
    delete remoteRepositories[connection.id]
    await loadAll()
    await router.push('/repositories')
  } catch (error) { toasts.error('Falha ao monitorar', error instanceof ApiError ? error.message : undefined) }
  finally { importingId.value = null }
}

async function configureWebhooks(connection: GitHubConnection): Promise<void> {
  if (!window.confirm('Criar webhooks nos repositórios monitorados? O token precisa de permissão de escrita em Webhooks.')) return
  try {
    const results = await api.post<WebhookConfigureResult[]>(`/github/connections/${connection.id}/configure-webhooks`, {})
    const ok = results.filter((item) => item.success).length
    const failed = results.length - ok
    failed ? toasts.warning(`${ok} webhook(s) configurado(s)`, `${failed} falharam.`) : toasts.success('Webhooks configurados', `${ok} repositório(s) atualizados.`)
  } catch (error) { toasts.error('Falha ao configurar webhooks', error instanceof ApiError ? error.message : undefined) }
}

async function changePassword(): Promise<void> {
  if (passwordForm.next !== passwordForm.confirmation) { toasts.warning('As senhas não coincidem'); return }
  if (passwordForm.next.length < 12) { toasts.warning('Senha muito curta', 'Use pelo menos 12 caracteres.'); return }
  changingPassword.value = true
  try { const message = await auth.changePassword(passwordForm.current, passwordForm.next); toasts.success('Senha alterada', message); await router.replace('/login') }
  catch (error) { toasts.error('Não foi possível alterar a senha', error instanceof ApiError ? error.message : undefined) }
  finally { changingPassword.value = false }
}

async function beginTwoFactor(): Promise<void> {
  if (!twoFactorPassword.value) { toasts.warning('Informe sua senha atual'); return }
  try { twoFactorSetup.value = await api.post<TwoFactorSetup>('/auth/2fa/setup', { current_password: twoFactorPassword.value }); twoFactorCode.value = '' }
  catch (error) { toasts.error('Não foi possível iniciar o 2FA', error instanceof ApiError ? error.message : undefined) }
}
async function confirmTwoFactor(): Promise<void> {
  try { twoFactor.value = await api.post<TwoFactorStatus>('/auth/2fa/confirm', { code: twoFactorCode.value }); twoFactorSetup.value = null; twoFactorCode.value = ''; twoFactorPassword.value = ''; toasts.success('2FA ativado', 'Sua conta agora exige o código do autenticador.') }
  catch (error) { toasts.error('Código inválido', error instanceof ApiError ? error.message : undefined) }
}
async function disableTwoFactor(): Promise<void> {
  if (!twoFactorPassword.value || !twoFactorCode.value) { toasts.warning('Informe a senha e o código 2FA'); return }
  if (!window.confirm('Desativar a autenticação em duas etapas desta conta?')) return
  try { const result = await api.post<MessageResponse>('/auth/2fa/disable', { current_password: twoFactorPassword.value, code: twoFactorCode.value }); toasts.success('2FA desativado', result.message); twoFactor.value = { enabled: false, confirmed_at: null, recovery_codes_remaining: 0 }; twoFactorPassword.value=''; twoFactorCode.value='' }
  catch (error) { toasts.error('Falha ao desativar 2FA', error instanceof ApiError ? error.message : undefined) }
}
async function revokeSession(session: SessionItem): Promise<void> { try { await api.delete<MessageResponse>(`/auth/sessions/${session.id}`); await loadAll() } catch (error) { toasts.error('Falha ao revogar sessão', error instanceof ApiError ? error.message : undefined) } }
async function requestBrowserPermission(): Promise<void> { if (!('Notification' in window)) return; browserPermission.value = await Notification.requestPermission() }
async function installPwa(): Promise<void> { const installed = await install(); if (installed) toasts.success('Aplicação instalada') }
function setTheme(value: ThemePreference): void { theme.setPreference(value) }
async function copyText(value: string): Promise<void> { await navigator.clipboard.writeText(value); toasts.success('Copiado') }
async function copyRecoveryCodes(): Promise<void> {
  if (!twoFactorSetup.value) return
  await copyText(twoFactorSetup.value.recovery_codes.join('\n'))
}

onMounted(loadAll)
</script>

<template>
  <div class="page-stack settings-page">
    <section class="page-heading"><div><span class="eyebrow">CONFIGURAÇÃO E SEGURANÇA</span><h2>Centro de controle</h2><p>Conta, 2FA, sessões, integração GitHub, monitoramento, PWA e aparência.</p></div><button class="button primary" @click="showConnectionForm = !showConnectionForm"><Plus :size="17" />Nova conexão</button></section>
    <section v-if="mustChangePassword" class="required-password"><AlertTriangle :size="20" /><div><strong>Troca de senha obrigatória</strong><p>Defina sua senha definitiva para continuar usando a plataforma.</p></div></section>

    <section class="settings-grid">
      <article class="settings-card"><header><div class="card-icon"><ShieldCheck :size="20" /></div><div><span>CONTA LOCAL</span><h3>Segurança de acesso</h3></div></header><div class="account-summary"><div class="large-avatar">{{ auth.user?.name?.slice(0,1).toUpperCase() }}</div><div><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span><small>{{ auth.user?.is_superuser ? 'Administrador da plataforma' : 'Usuário' }}</small></div></div><form class="password-form" @submit.prevent="changePassword"><label class="field"><span>Senha atual</span><input v-model="passwordForm.current" type="password" required /></label><label class="field"><span>Nova senha</span><input v-model="passwordForm.next" type="password" minlength="12" required /></label><label class="field"><span>Confirmar nova senha</span><input v-model="passwordForm.confirmation" type="password" minlength="12" required /></label><button class="button secondary full" :disabled="changingPassword"><KeyRound :size="16" />{{ changingPassword ? 'Alterando…' : 'Alterar senha e sair' }}</button></form></article>

      <article class="settings-card"><header><div class="card-icon"><LockKeyhole :size="20" /></div><div><span>AUTENTICAÇÃO FORTE</span><h3>2FA · TOTP</h3></div><StatusBadge :value="twoFactor.enabled ? 'success' : 'warning'" compact /></header><p class="card-copy">Compatível com Google Authenticator, Microsoft Authenticator, 1Password e outros apps TOTP.</p><div v-if="!twoFactor.enabled && !twoFactorSetup" class="security-form"><label class="field"><span>Confirme sua senha atual</span><input v-model="twoFactorPassword" type="password" /></label><button class="button primary" @click="beginTwoFactor"><ShieldCheck :size="16" />Configurar 2FA</button></div><div v-else-if="twoFactorSetup" class="twofa-setup"><img :src="twoFactorSetup.qr_data_uri" alt="QR Code do autenticador" /><div><strong>Escaneie o QR Code</strong><button class="secret-copy" @click="copyText(twoFactorSetup.secret)"><code>{{ twoFactorSetup.secret }}</code><Copy :size="14" /></button><label class="field"><span>Digite o código de 6 dígitos</span><input v-model="twoFactorCode" inputmode="numeric" autocomplete="one-time-code" maxlength="10" /></label><button class="button primary" @click="confirmTwoFactor"><CheckCircle2 :size="16" />Confirmar e ativar</button></div><div class="recovery-codes"><strong>Códigos de recuperação</strong><code v-for="code in twoFactorSetup.recovery_codes" :key="code">{{ code }}</code><button class="button ghost compact" @click="copyRecoveryCodes"><Copy :size="14" />Copiar todos</button></div></div><div v-else class="security-form"><div class="security-state"><CheckCircle2 :size="18" /><span><strong>2FA ativo</strong><small>{{ twoFactor.recovery_codes_remaining }} código(s) de recuperação disponível(is)</small></span></div><label class="field"><span>Senha atual para desativar</span><input v-model="twoFactorPassword" type="password" /></label><label class="field"><span>Código 2FA ou recuperação</span><input v-model="twoFactorCode" /></label><button class="button ghost danger-text" @click="disableTwoFactor">Desativar 2FA</button></div></article>
    </section>

    <section class="settings-card sessions-card"><header><div class="card-icon"><Smartphone :size="20" /></div><div><span>SESSÕES</span><h3>Dispositivos e acessos recentes</h3></div></header><div class="session-list"><article v-for="session in sessions" :key="session.id"><Smartphone :size="17" /><div><strong>{{ session.user_agent || 'Dispositivo não identificado' }}</strong><span>{{ session.ip_address || 'IP não informado' }} · criado {{ formatDateTime(session.created_at) }} · expira {{ formatDateTime(session.expires_at) }}</span></div><span :class="['session-status', session.revoked_at ? 'revoked' : 'active']">{{ session.revoked_at ? 'Revogada' : 'Ativa' }}</span><button v-if="!session.revoked_at" class="button ghost compact" @click="revokeSession(session)">Revogar</button></article></div></section>

    <section class="settings-card preferences-card"><header><div class="card-icon"><Smartphone :size="20" /></div><div><span>DISPOSITIVO</span><h3>PWA e aparência</h3></div></header><div class="preference-grid"><div><strong>Instalação como aplicativo</strong><span>{{ isStandalone ? 'PWA instalada neste dispositivo.' : 'Instale para abrir em modo aplicativo.' }}</span><button class="button secondary compact" :disabled="!canInstall || isStandalone" @click="installPwa"><Download :size="14" />{{ isStandalone ? 'Instalada' : 'Instalar' }}</button></div><div><strong>Avisos do navegador</strong><span>Permissão: {{ browserPermission }}</span><button class="button secondary compact" :disabled="browserPermission === 'granted' || browserPermission === 'unsupported'" @click="requestBrowserPermission"><BellRing :size="14" />Permitir</button></div><div class="theme-setting"><strong>Aparência</strong><div class="theme-options"><button :class="{ active: theme.preference === 'light' }" @click="setTheme('light')"><Sun :size="16" />Claro</button><button :class="{ active: theme.preference === 'dark' }" @click="setTheme('dark')"><Moon :size="16" />Escuro</button><button :class="{ active: theme.preference === 'system' }" @click="setTheme('system')"><Smartphone :size="16" />Sistema</button></div></div></div></section>

    <section class="github-section"><div class="section-heading"><div><span>INTEGRAÇÕES</span><h3>Contas GitHub e projetos monitorados</h3><p>Conectar valida o token; monitorar persiste o repositório imediatamente e a fila executa o detalhamento.</p></div><StatusBadge :value="realConnections.length ? 'success' : 'unknown'" /></div>
      <form v-if="showConnectionForm" class="connection-form" @submit.prevent="createConnection"><header><Github :size="22" /><div><strong>Conectar uma conta GitHub</strong><span>Para criar, excluir ou trocar a visibilidade de repositórios, o token precisa de Administration: write.</span></div></header><div class="form-grid"><label class="field"><span>Nome da conexão</span><input v-model="connectionForm.name" required /></label><label class="field"><span>URL da API</span><input v-model="connectionForm.api_url" type="url" required /></label><label class="field full-field"><span>Token de acesso</span><div class="input-with-icon"><KeyRound :size="17" /><input v-model="connectionForm.token" :type="showToken ? 'text' : 'password'" autocomplete="off" required /><button type="button" class="input-action" @click="showToken = !showToken"><EyeOff v-if="showToken" :size="16" /><Eye v-else :size="16" /></button></div></label></div><label class="check-row"><input v-model="connectionForm.auto_import" type="checkbox" /><span><strong>Monitorar automaticamente todos os repositórios acessíveis</strong><small>O catálogo aparece imediatamente; Actions/PRs/releases são processados em segundo plano.</small></span></label><footer><button type="button" class="button ghost" @click="showConnectionForm = false">Cancelar</button><button class="button primary" :disabled="savingConnection"><Link2 :size="16" />{{ savingConnection ? 'Validando…' : 'Validar e conectar' }}</button></footer></form>

      <div v-if="loading" class="connection-list"><div v-for="n in 2" :key="n" class="skeleton connection-skeleton" /></div><div v-else class="connection-list"><article v-for="connection in connections" :key="connection.id" class="connection-card"><div class="connection-main"><div class="github-avatar"><Github :size="21" /></div><div class="connection-copy"><div><strong>{{ connection.name }}</strong><StatusBadge :value="connection.status === 'active' ? 'success' : connection.status === 'demo' ? 'unknown' : 'failure'" compact /></div><span>@{{ connection.github_login }} · token final {{ connection.token_last_four || 'demo' }}</span><small>{{ connection.repository_count }} monitorado(s) · API {{ connection.rate_limit_remaining ?? '—' }} · sincronização {{ formatDateTime(connection.last_sync_at) }}</small></div></div><div v-if="connection.last_error" class="connection-error"><AlertTriangle :size="15" />{{ connection.last_error }}</div><div class="connection-actions"><button v-if="connection.status !== 'demo'" class="button ghost compact" @click="syncConnection(connection)"><RefreshCw :size="14" />Descobrir e sincronizar</button><button v-if="connection.status !== 'demo'" class="button ghost compact" @click="configureWebhooks(connection)"><Webhook :size="14" />Webhooks</button><button v-if="connection.status !== 'demo'" class="button ghost compact" @click="toggleRemote(connection)"><Database :size="14" />Projetos<ChevronUp v-if="activeConnectionId === connection.id" :size="13" /><ChevronDown v-else :size="13" /></button><RouterLink v-if="connection.status !== 'demo'" to="/jobs" class="button ghost compact"><ListChecks :size="14" />Fila</RouterLink><button class="button ghost compact danger-text" @click="removeConnection(connection)"><Trash2 :size="14" />Remover conexão</button></div>
        <div v-if="activeConnectionId === connection.id" class="remote-panel"><div v-if="remoteLoadingId === connection.id" class="remote-loading"><RefreshCw class="spin" :size="18" />Consultando GitHub…</div><template v-else><header><div><strong>Projetos acessíveis pelo token</strong><span>Itens já monitorados aparecem marcados.</span></div><div class="remote-search"><Search :size="15" /><input v-model="remoteQuery[connection.id]" placeholder="Buscar projeto…" /></div></header><div class="remote-toolbar"><span>{{ filteredRemote(connection.id).length }} encontrado(s) · {{ selectedRemote(connection.id).length }} selecionado(s)</span><button class="button ghost compact" @click="selectAllRemote(connection.id,true)">Selecionar todos</button><button class="button ghost compact" @click="selectAllRemote(connection.id,false)">Limpar</button><button class="button secondary compact" :disabled="importingId === connection.id" @click="monitorSelected(connection,false)"><Save :size="14" />Monitorar selecionados</button><button class="button primary compact" :disabled="importingId === connection.id" @click="monitorSelected(connection,true)">Monitorar todos</button></div><div class="remote-list"><label v-for="repo in filteredRemote(connection.id)" :key="repo.github_id" :class="{ monitored: repo.selected }"><input v-model="repo.selected" type="checkbox" /><Github :size="15" /><span><strong>{{ repo.full_name }}</strong><small>{{ repo.private ? 'Privado' : 'Público' }} · {{ repo.language || 'sem linguagem principal' }}</small></span><em v-if="repo.selected">MONITORADO</em></label></div></template></div>
      </article></div></section>
    <footer class="settings-footer">ARGWS Git Monitor · API FastAPI · PostgreSQL · Redis · RabbitMQ · Celery · Vue PWA <span>versão {{ appVersion }}</span></footer>
  </div>
</template>

<style scoped>
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.settings-card,.github-section{padding:1rem}.settings-card>header{display:flex;align-items:center;gap:.65rem;padding-bottom:.8rem;border-bottom:1px solid var(--border-soft)}.settings-card>header>div:nth-child(2){display:grid}.settings-card header span,.section-heading>div>span{color:var(--primary-strong);font-size:.6rem;font-weight:850;letter-spacing:.12em}.settings-card h3{margin:0;color:var(--text-strong);font-size:.92rem}.account-summary{display:flex;align-items:center;gap:.7rem;padding:.9rem 0}.large-avatar{display:grid;place-items:center;width:2.8rem;height:2.8rem;color:white;border-radius:.8rem;background:linear-gradient(135deg,var(--primary),var(--secondary));font-weight:850}.account-summary>div:last-child{display:grid}.account-summary span,.account-summary small{color:var(--text-muted);font-size:.66rem}.password-form,.security-form{display:grid;gap:.7rem}.card-copy{color:var(--text-muted);font-size:.72rem}.security-state{display:flex;align-items:center;gap:.6rem;padding:.7rem;color:var(--success);border-radius:.7rem;background:color-mix(in srgb,var(--success) 8%,var(--surface))}.security-state span{display:grid}.security-state strong{color:var(--text-strong)}.security-state small{color:var(--text-muted)}.twofa-setup{display:grid;grid-template-columns:150px 1fr;gap:1rem;margin-top:.8rem}.twofa-setup img{width:150px;border:1px solid var(--border);border-radius:.75rem;background:white;padding:.35rem}.twofa-setup>div{display:grid;align-content:start;gap:.65rem}.secret-copy{display:flex;align-items:center;gap:.4rem;width:max-content;max-width:100%;padding:.45rem;color:var(--text);border:1px solid var(--border);border-radius:.5rem;background:var(--surface-soft);cursor:pointer}.recovery-codes{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:.35rem;padding:.7rem;border:1px dashed var(--border);border-radius:.75rem}.recovery-codes strong,.recovery-codes .button{grid-column:1/-1}.recovery-codes code{padding:.35rem;text-align:center;color:var(--text-strong);background:var(--surface-soft);border-radius:.4rem}.sessions-card{display:grid;gap:.7rem}.session-list{display:grid}.session-list article{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:.65rem;padding:.7rem;border-bottom:1px solid var(--border-soft)}.session-list article:last-child{border-bottom:0}.session-list article>div{display:grid;min-width:0}.session-list strong{overflow:hidden;color:var(--text-strong);font-size:.72rem;text-overflow:ellipsis;white-space:nowrap}.session-list span{color:var(--text-muted);font-size:.62rem}.session-status{padding:.2rem .4rem;border-radius:999px;font-weight:800}.session-status.active{color:var(--success);background:color-mix(in srgb,var(--success) 8%,var(--surface))}.session-status.revoked{color:var(--text-subtle)}.preference-grid{display:grid;grid-template-columns:1fr 1fr 2fr;gap:1rem;padding-top:.8rem}.preference-grid>div{display:grid;align-content:start;gap:.45rem}.preference-grid strong{color:var(--text-strong);font-size:.72rem}.preference-grid span{color:var(--text-muted);font-size:.65rem}.theme-options{display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem}.theme-options button{display:flex;align-items:center;justify-content:center;gap:.35rem;min-height:2.4rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.65rem;background:var(--surface-soft);cursor:pointer}.theme-options button.active{color:var(--primary-strong);border-color:var(--primary);background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.required-password{display:flex;gap:.7rem;padding:.8rem;color:var(--warning);border:1px solid color-mix(in srgb,var(--warning) 30%,var(--border));border-radius:.8rem;background:color-mix(in srgb,var(--warning) 7%,var(--surface))}.required-password p{margin:.1rem 0;color:var(--text-muted);font-size:.7rem}.github-section{border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.section-heading{padding-bottom:.8rem;border-bottom:1px solid var(--border-soft)}.connection-form{display:grid;gap:.8rem;margin-top:.8rem;padding:.9rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised)}.connection-form header{display:flex;gap:.6rem}.connection-form header>div{display:grid}.connection-form header span{color:var(--text-muted);font-size:.68rem}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.full-field{grid-column:1/-1}.check-row{display:flex;gap:.55rem;align-items:flex-start}.check-row span{display:grid}.check-row strong{color:var(--text-strong);font-size:.72rem}.check-row small{color:var(--text-muted);font-size:.65rem}.connection-form footer{display:flex;justify-content:flex-end;gap:.5rem}.connection-list{display:grid;gap:.7rem;margin-top:.8rem}.connection-skeleton{height:120px;border-radius:.8rem}.connection-card{overflow:hidden;border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised)}.connection-main{display:flex;align-items:center;gap:.7rem;padding:.8rem}.github-avatar{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:.75rem;background:var(--surface-soft)}.connection-copy{display:grid;min-width:0}.connection-copy>div{display:flex;align-items:center;gap:.4rem}.connection-copy strong{color:var(--text-strong)}.connection-copy span,.connection-copy small{color:var(--text-muted);font-size:.65rem}.connection-error{display:flex;gap:.4rem;padding:.5rem .8rem;color:var(--danger);font-size:.66rem;background:color-mix(in srgb,var(--danger) 6%,var(--surface))}.connection-actions{display:flex;flex-wrap:wrap;gap:.4rem;padding:.6rem .8rem;border-top:1px solid var(--border-soft)}.remote-panel{padding:.8rem;border-top:1px solid var(--border);background:var(--surface)}.remote-panel>header{display:flex;align-items:center;justify-content:space-between;gap:.7rem}.remote-panel header>div:first-child{display:grid}.remote-panel header strong{color:var(--text-strong);font-size:.72rem}.remote-panel header span{color:var(--text-muted);font-size:.62rem}.remote-search{display:flex;align-items:center;gap:.4rem;padding:0 .55rem;border:1px solid var(--border);border-radius:.6rem;background:var(--surface-soft)}.remote-search input{min-height:2.2rem;border:0;outline:0;background:transparent;color:var(--text)}.remote-toolbar{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:.4rem;margin:.7rem 0}.remote-toolbar>span{margin-right:auto;color:var(--text-muted);font-size:.62rem}.remote-list{display:grid;grid-template-columns:1fr 1fr;max-height:390px;overflow:auto;border:1px solid var(--border);border-radius:.65rem}.remote-list label{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.45rem;padding:.55rem;border-bottom:1px solid var(--border-soft);cursor:pointer}.remote-list label.monitored{background:color-mix(in srgb,var(--success) 5%,var(--surface))}.remote-list span{display:grid;min-width:0}.remote-list strong{overflow:hidden;color:var(--text-strong);font-size:.66rem;text-overflow:ellipsis;white-space:nowrap}.remote-list small{color:var(--text-muted);font-size:.58rem}.remote-list em{color:var(--success);font-size:.52rem;font-style:normal;font-weight:850}.remote-loading{display:flex;justify-content:center;gap:.5rem;padding:2rem;color:var(--text-muted)}.settings-footer{display:flex;justify-content:space-between;color:var(--text-muted);font-size:.62rem;border-top:1px solid var(--border);padding:.7rem}.settings-footer span{margin-left:auto}
@media(max-width:900px){.settings-grid{grid-template-columns:1fr}.preference-grid{grid-template-columns:1fr}.remote-list{grid-template-columns:1fr}.twofa-setup{grid-template-columns:120px 1fr}.twofa-setup img{width:120px}.recovery-codes{grid-template-columns:1fr 1fr}}@media(max-width:600px){.form-grid{grid-template-columns:1fr}.full-field{grid-column:auto}.session-list article{grid-template-columns:auto 1fr}.session-list .session-status,.session-list .button{grid-column:2}.remote-panel>header{align-items:stretch;flex-direction:column}.remote-search{width:100%}.remote-search input{width:100%}.remote-toolbar .button{flex:1 1 130px}.twofa-setup{grid-template-columns:1fr}.twofa-setup img{width:160px;justify-self:center}.recovery-codes{grid-column:auto}.settings-footer{display:grid;gap:.3rem}.settings-footer span{margin:0}}
</style>
