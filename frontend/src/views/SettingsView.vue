<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  Activity, AlertTriangle, BellRing, CheckCircle2, ChevronDown, ChevronUp, Copy,
  Database, FileText, Github, KeyRound, Link2, ListChecks, LockKeyhole, Moon,
  Network, Plus, RefreshCw, Search, Server, ShieldCheck, Smartphone, Sun, Trash2,
  UserRound, Webhook, Wrench
} from 'lucide-vue-next'
import StatusBadge from '../components/StatusBadge.vue'
import { usePwaInstall } from '../composables/usePwaInstall'
import { ApiError, api } from '../services/api'
import { formatDateTime, formatRelative } from '../services/format'
import { useAuthStore } from '../stores/auth'
import { useThemeStore, type ThemePreference } from '../stores/theme'
import { useToastStore } from '../stores/toast'
import type {
  GitHubConnection, MessageResponse, RemoteRepository, RepositoryImportResponse,
  RuntimeStatus, SessionItem, SyncResponse, TwoFactorSetup, TwoFactorStatus,
  WebhookConfigureResult
} from '../types/api'

type SettingsTab = 'github' | 'security' | 'preferences' | 'system'

interface ConnectionDiagnostics {
  connected: boolean
  github_login: string
  accessible_repositories: number
  private_repositories: number
  writable_repositories: number
  admin_repositories: number
  actions_samples_checked: number
  actions_samples_observed: number
  rate_limit_remaining: number | null
  rate_limit_reset_at: string | null
  oauth_scopes: string[]
  warnings: string[]
  checked_at: string
}

const auth = useAuthStore()
const theme = useThemeStore()
const toasts = useToastStore()
const route = useRoute()
const router = useRouter()
const { canInstall, isStandalone, install } = usePwaInstall()

const tab = ref<SettingsTab>('github')
const loading = ref(true)
const runtime = ref<RuntimeStatus | null>(null)
const connections = ref<GitHubConnection[]>([])
const sessions = ref<SessionItem[]>([])
const diagnostics = reactive<Record<string, ConnectionDiagnostics>>({})
const diagnosticLoading = ref<string | null>(null)
const activeConnectionId = ref<string | null>(null)
const remoteLoadingId = ref<string | null>(null)
const remoteRepositories = reactive<Record<string, RemoteRepository[]>>({})
const remoteQuery = reactive<Record<string, string>>({})
const importingId = ref<string | null>(null)
const syncingId = ref<string | null>(null)
const webhookId = ref<string | null>(null)
const showConnectionForm = ref(false)
const showToken = ref(false)
const savingConnection = ref(false)

const twoFactor = ref<TwoFactorStatus>({ enabled: false, confirmed_at: null, recovery_codes_remaining: 0 })
const twoFactorSetup = ref<TwoFactorSetup | null>(null)
const twoFactorPassword = ref('')
const twoFactorCode = ref('')
const passwordForm = reactive({ current: '', next: '', confirmation: '' })
const changingPassword = ref(false)
const browserPermission = ref<'default' | 'denied' | 'granted' | 'unsupported'>(
  'Notification' in window ? Notification.permission : 'unsupported'
)
const connectionForm = reactive({
  name: 'GitHub principal',
  token: '',
  auto_import: true,
  api_url: 'https://api.github.com'
})

const mustChangePassword = computed(() => auth.user?.must_change_password || route.query.password === 'required')
const realConnections = computed(() => connections.value.filter((item) => item.status !== 'demo'))
const avatarInitials = computed(() =>
  (auth.user?.name || 'U').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
)
const runtimeHealthy = computed(() =>
  runtime.value?.database === 'ok' && runtime.value?.redis === 'ok' && runtime.value?.worker_online
)

const tabs: Array<{ key: SettingsTab; label: string; icon: typeof Github }> = [
  { key: 'github', label: 'GitHub e coleta', icon: Github },
  { key: 'security', label: 'Conta e segurança', icon: ShieldCheck },
  { key: 'preferences', label: 'Preferências', icon: Sun },
  { key: 'system', label: 'Sistema', icon: Server }
]

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    const [loadedConnections, loaded2fa, loadedSessions, loadedRuntime] = await Promise.all([
      api.get<GitHubConnection[]>('/github/connections'),
      api.get<TwoFactorStatus>('/auth/2fa/status'),
      api.get<SessionItem[]>('/auth/sessions'),
      api.get<RuntimeStatus>('/system/runtime')
    ])
    connections.value = loadedConnections
    twoFactor.value = loaded2fa
    sessions.value = loadedSessions
    runtime.value = loadedRuntime
    if (!realConnections.value.length) showConnectionForm.value = true
  } catch (error) {
    toasts.error('Falha ao carregar configurações', error instanceof ApiError ? error.message : undefined)
  } finally {
    loading.value = false
  }
}

async function createConnection(): Promise<void> {
  if (!connectionForm.token.trim()) return
  savingConnection.value = true
  try {
    const created = await api.post<GitHubConnection>('/github/connections', {
      name: connectionForm.name.trim(),
      token: connectionForm.token.trim(),
      auto_import: connectionForm.auto_import,
      api_url: connectionForm.api_url.trim()
    })
    connectionForm.token = ''
    showConnectionForm.value = false
    toasts.success(
      'GitHub conectado',
      `${created.available_repository_count || created.repository_count} repositório(s) acessíveis. Execute o diagnóstico para conferir Actions e permissões.`
    )
    await loadAll()
    await diagnose(created)
  } catch (error) {
    toasts.error('Não foi possível conectar', error instanceof ApiError ? error.message : undefined)
  } finally {
    savingConnection.value = false
  }
}

async function diagnose(connection: GitHubConnection): Promise<void> {
  diagnosticLoading.value = connection.id
  try {
    diagnostics[connection.id] = await api.get<ConnectionDiagnostics>(
      `/github/connections/${connection.id}/diagnostics`
    )
    const result = diagnostics[connection.id]
    if (result.warnings.length) {
      toasts.warning('Diagnóstico concluído com alertas', `${result.warnings.length} alerta(s) de permissão/coleta.`)
    } else {
      toasts.success('Conexão validada', `${result.actions_samples_observed}/${result.actions_samples_checked} amostra(s) de Actions observada(s).`)
    }
  } catch (error) {
    toasts.error('Diagnóstico GitHub falhou', error instanceof ApiError ? error.message : undefined)
  } finally {
    diagnosticLoading.value = null
  }
}

async function syncConnection(connection: GitHubConnection): Promise<void> {
  syncingId.value = connection.id
  try {
    const result = await api.post<SyncResponse>(`/github/connections/${connection.id}/sync`)
    toasts.success('Sincronização enviada', `${result.message} Acompanhe o processamento na Fila.`)
    await loadAll()
  } catch (error) {
    toasts.error('Sincronização recusada', error instanceof ApiError ? error.message : undefined)
  } finally {
    syncingId.value = null
  }
}

async function removeConnection(connection: GitHubConnection): Promise<void> {
  const typed = window.prompt(
    `Remover a conexão “${connection.name}” e os dados locais monitorados?\nOs repositórios do GitHub NÃO serão excluídos.\n\nDigite: ${connection.github_login}`
  )
  if (typed !== connection.github_login) return
  try {
    const result = await api.delete<MessageResponse>(`/github/connections/${connection.id}`)
    delete remoteRepositories[connection.id]
    delete diagnostics[connection.id]
    toasts.success('Conexão removida', result.message)
    await loadAll()
  } catch (error) {
    toasts.error('Não foi possível remover', error instanceof ApiError ? error.message : undefined)
  }
}

async function toggleRemote(connection: GitHubConnection): Promise<void> {
  if (activeConnectionId.value === connection.id) {
    activeConnectionId.value = null
    return
  }
  activeConnectionId.value = connection.id
  if (remoteRepositories[connection.id]) return
  remoteLoadingId.value = connection.id
  try {
    remoteRepositories[connection.id] = await api.get<RemoteRepository[]>(
      `/github/connections/${connection.id}/remote-repositories`
    )
  } catch (error) {
    toasts.error('Falha ao consultar projetos', error instanceof ApiError ? error.message : undefined)
  } finally {
    remoteLoadingId.value = null
  }
}

function filteredRemote(connectionId: string): RemoteRepository[] {
  const term = (remoteQuery[connectionId] || '').trim().toLowerCase()
  const items = remoteRepositories[connectionId] || []
  if (!term) return items
  return items.filter((item) =>
    item.full_name.toLowerCase().includes(term)
    || (item.language || '').toLowerCase().includes(term)
    || (item.description || '').toLowerCase().includes(term)
  )
}

function selectedRemote(connectionId: string): number[] {
  return (remoteRepositories[connectionId] || [])
    .filter((item) => item.selected)
    .map((item) => item.github_id)
}

function selectFiltered(connectionId: string, selected: boolean): void {
  for (const item of filteredRemote(connectionId)) item.selected = selected
}

async function monitorSelected(connection: GitHubConnection, all = false): Promise<void> {
  const source = remoteRepositories[connection.id] || []
  const ids = all ? source.map((item) => item.github_id) : selectedRemote(connection.id)
  if (!ids.length) {
    toasts.info('Selecione projetos', 'Marque ao menos um repositório para adicionar/ressincronizar.')
    return
  }
  importingId.value = connection.id
  try {
    const result = await api.post<RepositoryImportResponse>(
      `/github/connections/${connection.id}/import`,
      { repository_ids: ids }
    )
    toasts.success(
      'Monitoramento atualizado',
      `${result.imported_count} novo(s), ${result.already_monitored_count} já monitorado(s); 1 lote de sincronização criado.`
    )
    delete remoteRepositories[connection.id]
    await loadAll()
  } catch (error) {
    toasts.error('Falha ao monitorar', error instanceof ApiError ? error.message : undefined)
  } finally {
    importingId.value = null
  }
}

async function configureWebhooks(connection: GitHubConnection): Promise<void> {
  if (!window.confirm(
    'Configurar webhooks para push, PR, Actions, releases e issues nos projetos monitorados? O token precisa de Webhooks: write.'
  )) return
  webhookId.value = connection.id
  try {
    const results = await api.post<WebhookConfigureResult[]>(
      `/github/connections/${connection.id}/configure-webhooks`,
      {}
    )
    const ok = results.filter((item) => item.success).length
    const failed = results.length - ok
    if (failed) toasts.warning(`${ok} webhook(s) configurado(s)`, `${failed} falharam; verifique Administration/Webhooks.`)
    else toasts.success('Webhooks configurados', `${ok} repositório(s) atualizados.`)
  } catch (error) {
    toasts.error('Falha ao configurar webhooks', error instanceof ApiError ? error.message : undefined)
  } finally {
    webhookId.value = null
  }
}

async function changePassword(): Promise<void> {
  if (passwordForm.next !== passwordForm.confirmation) {
    toasts.warning('As senhas não coincidem')
    return
  }
  if (passwordForm.next.length < 12) {
    toasts.warning('Senha muito curta', 'Use pelo menos 12 caracteres.')
    return
  }
  changingPassword.value = true
  try {
    const message = await auth.changePassword(passwordForm.current, passwordForm.next)
    toasts.success('Senha alterada', message)
    await router.replace('/login')
  } catch (error) {
    toasts.error('Não foi possível alterar a senha', error instanceof ApiError ? error.message : undefined)
  } finally {
    changingPassword.value = false
  }
}

async function beginTwoFactor(): Promise<void> {
  if (!twoFactorPassword.value) {
    toasts.warning('Informe sua senha atual')
    return
  }
  try {
    twoFactorSetup.value = await api.post<TwoFactorSetup>('/auth/2fa/setup', {
      current_password: twoFactorPassword.value
    })
    twoFactorCode.value = ''
  } catch (error) {
    toasts.error('Não foi possível iniciar o 2FA', error instanceof ApiError ? error.message : undefined)
  }
}

async function confirmTwoFactor(): Promise<void> {
  try {
    twoFactor.value = await api.post<TwoFactorStatus>('/auth/2fa/confirm', { code: twoFactorCode.value })
    twoFactorSetup.value = null
    twoFactorCode.value = ''
    twoFactorPassword.value = ''
    await auth.refreshUser()
    toasts.success('2FA ativado', 'Sua conta agora exige o código do autenticador.')
  } catch (error) {
    toasts.error('Código inválido', error instanceof ApiError ? error.message : undefined)
  }
}

async function disableTwoFactor(): Promise<void> {
  if (!twoFactorPassword.value || !twoFactorCode.value) {
    toasts.warning('Informe a senha e o código 2FA')
    return
  }
  if (!window.confirm('Desativar a autenticação em duas etapas desta conta?')) return
  try {
    const result = await api.post<MessageResponse>('/auth/2fa/disable', {
      current_password: twoFactorPassword.value,
      code: twoFactorCode.value
    })
    twoFactor.value = { enabled: false, confirmed_at: null, recovery_codes_remaining: 0 }
    twoFactorPassword.value = ''
    twoFactorCode.value = ''
    await auth.refreshUser()
    toasts.success('2FA desativado', result.message)
  } catch (error) {
    toasts.error('Falha ao desativar 2FA', error instanceof ApiError ? error.message : undefined)
  }
}

async function revokeSession(session: SessionItem): Promise<void> {
  try {
    await api.delete<MessageResponse>(`/auth/sessions/${session.id}`)
    await loadAll()
  } catch (error) {
    toasts.error('Falha ao revogar sessão', error instanceof ApiError ? error.message : undefined)
  }
}

async function revokeAllSessions(): Promise<void> {
  if (!window.confirm('Revogar todas as suas sessões? Você precisará entrar novamente.')) return
  try {
    await api.post<MessageResponse>('/auth/sessions/revoke-all')
    await auth.logout()
    await router.replace('/login')
  } catch (error) {
    toasts.error('Falha ao revogar sessões', error instanceof ApiError ? error.message : undefined)
  }
}

async function requestBrowserPermission(): Promise<void> {
  if (!('Notification' in window)) return
  browserPermission.value = await Notification.requestPermission()
}

async function installPwa(): Promise<void> {
  const installed = await install()
  if (installed) toasts.success('Aplicação instalada')
}

function setTheme(value: ThemePreference): void {
  theme.setPreference(value)
}

async function copyText(value: string): Promise<void> {
  await navigator.clipboard.writeText(value)
  toasts.success('Copiado')
}

async function copyRecoveryCodes(): Promise<void> {
  if (!twoFactorSetup.value) return
  await copyText(twoFactorSetup.value.recovery_codes.join('\n'))
}

onMounted(async () => {
  if (route.query.tab === 'security' || mustChangePassword.value) tab.value = 'security'
  await loadAll()
})
</script>

<template>
  <div class="page-stack settings-page">
    <section class="page-heading">
      <div>
        <span class="eyebrow">CENTRO DE CONTROLE</span>
        <h2>Configurações</h2>
        <p>Integração GitHub, diagnóstico de coleta, segurança, preferências e estado real da stack.</p>
      </div>
      <button v-if="tab === 'github'" class="button primary" @click="showConnectionForm = !showConnectionForm">
        <Plus :size="16" />Nova conexão
      </button>
      <button v-else class="button secondary" :disabled="loading" @click="loadAll">
        <RefreshCw :size="16" :class="{ spin: loading }" />Atualizar
      </button>
    </section>

    <section v-if="mustChangePassword" class="required-password">
      <AlertTriangle :size="20" />
      <div><strong>Troca de senha obrigatória</strong><p>Defina uma senha definitiva antes de acessar os demais módulos.</p></div>
    </section>

    <nav class="settings-tabs" aria-label="Seções de configuração">
      <button v-for="item in tabs" :key="item.key" :class="{ active: tab === item.key }" @click="tab = item.key">
        <component :is="item.icon" :size="17" /><span>{{ item.label }}</span>
      </button>
    </nav>

    <template v-if="tab === 'github'">
      <section class="github-explain">
        <Network :size="21" />
        <div>
          <strong>Como o monitoramento funciona agora</strong>
          <p>Webhooks atualizam push, Pull Requests, Actions, releases e issues imediatamente. O full-sync periódico serve como reconciliação e roda no mínimo a cada 1 hora para não esgotar o rate limit REST em contas com centenas de projetos.</p>
        </div>
        <RouterLink class="button ghost compact" to="/jobs"><ListChecks :size="14" />Ver Fila</RouterLink>
      </section>

      <section v-if="showConnectionForm" class="connection-form-panel">
        <header><div><span class="eyebrow">NOVA CONEXÃO</span><h3>Conectar GitHub</h3></div></header>
        <form @submit.prevent="createConnection">
          <label class="field"><span>Nome da conexão</span><input v-model="connectionForm.name" required maxlength="120" /></label>
          <label class="field"><span>API URL</span><input v-model="connectionForm.api_url" required /></label>
          <label class="field token-field"><span>Token GitHub</span><div><input v-model="connectionForm.token" :type="showToken ? 'text' : 'password'" autocomplete="off" placeholder="github_pat_… ou ghp_…" required /><button type="button" @click="showToken = !showToken">{{ showToken ? 'Ocultar' : 'Mostrar' }}</button></div></label>
          <label class="check-line"><input v-model="connectionForm.auto_import" type="checkbox" /><span>Descobrir e adicionar automaticamente os projetos acessíveis</span></label>
          <button class="button primary" :disabled="savingConnection">{{ savingConnection ? 'Validando…' : 'Conectar e validar' }}</button>
        </form>
        <div class="permission-grid">
          <span><strong>Metadata</strong> read</span><span><strong>Contents</strong> read</span><span><strong>Actions</strong> read/write</span><span><strong>Pull requests</strong> read</span><span><strong>Issues</strong> read/write</span><span><strong>Administration</strong> write</span><span><strong>Webhooks</strong> write</span><span><strong>Packages</strong> read/write/delete</span>
        </div>
        <p>O token nunca é enviado ao frontend depois de salvo; fica criptografado no backend. As permissões efetivas são validadas pelo diagnóstico.</p>
      </section>

      <section v-if="!realConnections.length && !loading" class="empty-connections">
        <Github :size="34" /><strong>Nenhuma conta GitHub operacional</strong><p>Adicione uma conexão para listar seus projetos públicos e privados.</p>
      </section>

      <section class="connections-list">
        <article v-for="connection in realConnections" :key="connection.id" class="connection-card">
          <header>
            <div class="github-mark"><Github :size="22" /></div>
            <div class="connection-title"><strong>{{ connection.name }}</strong><span>@{{ connection.github_login }} · token ••••{{ connection.token_last_four || '----' }}</span></div>
            <StatusBadge :value="connection.status" compact />
          </header>

          <div class="connection-metrics">
            <div><strong>{{ connection.repository_count }}</strong><span>monitorados</span></div>
            <div><strong>{{ diagnostics[connection.id]?.accessible_repositories ?? connection.available_repository_count }}</strong><span>acessíveis</span></div>
            <div><strong>{{ diagnostics[connection.id]?.private_repositories ?? '—' }}</strong><span>privados</span></div>
            <div><strong>{{ diagnostics[connection.id]?.writable_repositories ?? '—' }}</strong><span>com escrita</span></div>
            <div><strong>{{ diagnostics[connection.id]?.rate_limit_remaining ?? connection.rate_limit_remaining ?? '—' }}</strong><span>rate limit</span></div>
          </div>

          <div class="connection-health">
            <span><strong>Última sync:</strong> {{ formatRelative(connection.last_sync_at) }}</span>
            <span v-if="diagnostics[connection.id]"><strong>Actions amostradas:</strong> {{ diagnostics[connection.id].actions_samples_observed }}/{{ diagnostics[connection.id].actions_samples_checked }}</span>
            <span v-if="diagnostics[connection.id]?.admin_repositories"><strong>Admin:</strong> {{ diagnostics[connection.id].admin_repositories }} repo(s)</span>
          </div>

          <div v-if="connection.last_error" class="connection-error"><AlertTriangle :size="15" /><span>{{ connection.last_error }}</span></div>
          <div v-if="diagnostics[connection.id]?.warnings.length" class="connection-error warning"><AlertTriangle :size="15" /><details><summary>{{ diagnostics[connection.id].warnings.length }} alerta(s) de API/permissão</summary><ul><li v-for="warning in diagnostics[connection.id].warnings" :key="warning">{{ warning }}</li></ul></details></div>

          <div class="connection-actions">
            <button class="button secondary compact" :disabled="diagnosticLoading === connection.id" @click="diagnose(connection)"><ShieldCheck :size="14" />{{ diagnosticLoading === connection.id ? 'Diagnosticando…' : 'Diagnosticar' }}</button>
            <button class="button secondary compact" :disabled="syncingId === connection.id" @click="syncConnection(connection)"><RefreshCw :size="14" :class="{ spin: syncingId === connection.id }" />Sincronizar</button>
            <button class="button secondary compact" :disabled="webhookId === connection.id" @click="configureWebhooks(connection)"><Webhook :size="14" />Webhooks</button>
            <button class="button ghost compact" @click="toggleRemote(connection)"><Search :size="14" />Projetos<ChevronUp v-if="activeConnectionId === connection.id" :size="14" /><ChevronDown v-else :size="14" /></button>
            <button class="button ghost compact danger-text" @click="removeConnection(connection)"><Trash2 :size="14" />Remover</button>
          </div>

          <section v-if="activeConnectionId === connection.id" class="remote-projects">
            <div v-if="remoteLoadingId === connection.id" class="remote-loading"><span v-for="n in 4" :key="n" class="skeleton" /></div>
            <template v-else>
              <header>
                <label><Search :size="15" /><input v-model="remoteQuery[connection.id]" placeholder="Buscar owner/repo, linguagem ou descrição…" /></label>
                <div><button class="button ghost compact" @click="selectFiltered(connection.id, true)">Selecionar filtrados</button><button class="button ghost compact" @click="selectFiltered(connection.id, false)">Desmarcar filtrados</button></div>
              </header>
              <div class="remote-list">
                <label v-for="repo in filteredRemote(connection.id)" :key="repo.github_id" :class="{ selected: repo.selected }">
                  <input v-model="repo.selected" type="checkbox" />
                  <div><strong>{{ repo.full_name }}</strong><span>{{ repo.private ? 'Privado' : 'Público' }} · {{ repo.default_branch }}<template v-if="repo.language"> · {{ repo.language }}</template></span><small>{{ repo.description || 'Sem descrição' }}</small></div>
                  <em v-if="repo.permissions.admin">admin</em><em v-else-if="repo.permissions.push">write</em><em v-else>read</em>
                </label>
              </div>
              <footer><span>{{ selectedRemote(connection.id).length }} selecionado(s)</span><div><button class="button secondary compact" :disabled="importingId === connection.id" @click="monitorSelected(connection, true)">Monitorar todos</button><button class="button primary compact" :disabled="importingId === connection.id || !selectedRemote(connection.id).length" @click="monitorSelected(connection)">{{ importingId === connection.id ? 'Enviando…' : 'Adicionar/ressincronizar selecionados' }}</button></div></footer>
            </template>
          </section>
        </article>
      </section>
    </template>

    <template v-else-if="tab === 'security'">
      <section class="security-layout">
        <article class="settings-card profile-summary-card">
          <header><div class="card-icon"><UserRound :size="20" /></div><div><span>PERFIL</span><h3>Identidade da conta</h3></div></header>
          <div class="profile-summary">
            <div class="large-avatar"><img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" :alt="auth.user.name" /><span v-else>{{ avatarInitials }}</span></div>
            <div><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span><small>{{ auth.user?.job_title || (auth.user?.is_superuser ? 'Administrador' : 'Usuário') }}</small></div>
          </div>
          <RouterLink class="button secondary full" to="/profile"><UserRound :size="15" />Editar perfil e foto</RouterLink>
        </article>

        <article class="settings-card">
          <header><div class="card-icon"><KeyRound :size="20" /></div><div><span>SENHA</span><h3>Credencial local</h3></div></header>
          <form class="password-form" @submit.prevent="changePassword">
            <label class="field"><span>Senha atual</span><input v-model="passwordForm.current" type="password" autocomplete="current-password" required /></label>
            <label class="field"><span>Nova senha</span><input v-model="passwordForm.next" type="password" autocomplete="new-password" minlength="12" required /></label>
            <label class="field"><span>Confirmar nova senha</span><input v-model="passwordForm.confirmation" type="password" autocomplete="new-password" minlength="12" required /></label>
            <button class="button secondary full" :disabled="changingPassword"><KeyRound :size="15" />{{ changingPassword ? 'Alterando…' : 'Alterar senha e encerrar sessões' }}</button>
          </form>
        </article>

        <article class="settings-card twofa-card">
          <header><div class="card-icon"><LockKeyhole :size="20" /></div><div><span>AUTENTICAÇÃO FORTE</span><h3>2FA · TOTP</h3></div><StatusBadge :value="twoFactor.enabled ? 'success' : 'warning'" compact /></header>
          <p class="card-copy">Google Authenticator, Microsoft Authenticator, 1Password e qualquer aplicativo TOTP compatível.</p>
          <div v-if="!twoFactor.enabled && !twoFactorSetup" class="security-form">
            <label class="field"><span>Confirme sua senha atual</span><input v-model="twoFactorPassword" type="password" /></label>
            <button class="button primary" @click="beginTwoFactor"><ShieldCheck :size="15" />Configurar 2FA</button>
          </div>
          <div v-else-if="twoFactorSetup" class="twofa-setup">
            <img :src="twoFactorSetup.qr_data_uri" alt="QR Code TOTP" />
            <div class="twofa-main"><strong>Escaneie o QR Code</strong><button class="secret-copy" @click="copyText(twoFactorSetup.secret)"><code>{{ twoFactorSetup.secret }}</code><Copy :size="14" /></button><label class="field"><span>Código de 6 dígitos</span><input v-model="twoFactorCode" inputmode="numeric" autocomplete="one-time-code" /></label><button class="button primary" @click="confirmTwoFactor"><CheckCircle2 :size="15" />Confirmar e ativar</button></div>
            <div class="recovery-codes"><strong>Guarde os códigos de recuperação</strong><code v-for="code in twoFactorSetup.recovery_codes" :key="code">{{ code }}</code><button class="button ghost compact" @click="copyRecoveryCodes"><Copy :size="14" />Copiar todos</button></div>
          </div>
          <div v-else class="security-form"><div class="security-state"><CheckCircle2 :size="18" /><span><strong>2FA ativo</strong><small>{{ twoFactor.recovery_codes_remaining }} código(s) de recuperação restante(s)</small></span></div><label class="field"><span>Senha atual</span><input v-model="twoFactorPassword" type="password" /></label><label class="field"><span>Código 2FA ou recuperação</span><input v-model="twoFactorCode" /></label><button class="button ghost danger-text" @click="disableTwoFactor">Desativar 2FA</button></div>
        </article>
      </section>

      <section class="settings-card sessions-card">
        <header><div class="card-icon"><Smartphone :size="20" /></div><div><span>SESSÕES</span><h3>Dispositivos e acessos</h3></div><button class="button ghost compact danger-text" @click="revokeAllSessions">Revogar todas</button></header>
        <div class="session-list">
          <article v-for="session in sessions" :key="session.id" :class="{ revoked: session.revoked_at }"><Smartphone :size="17" /><div><strong>{{ session.user_agent || 'Dispositivo não identificado' }}</strong><span>{{ session.ip_address || 'IP não informado' }} · criada {{ formatDateTime(session.created_at) }}</span><small>{{ session.revoked_at ? `Revogada ${formatDateTime(session.revoked_at)}` : `Expira ${formatDateTime(session.expires_at)}` }}</small></div><button v-if="!session.revoked_at" class="button ghost compact" @click="revokeSession(session)">Revogar</button></article>
        </div>
      </section>
    </template>

    <template v-else-if="tab === 'preferences'">
      <section class="preference-grid">
        <article class="settings-card">
          <header><div class="card-icon"><Sun :size="20" /></div><div><span>APARÊNCIA</span><h3>Tema da interface</h3></div></header>
          <div class="theme-grid"><button :class="{ active: theme.preference === 'light' }" @click="setTheme('light')"><Sun :size="22" /><strong>Claro</strong><span>Maior legibilidade e contraste</span></button><button :class="{ active: theme.preference === 'dark' }" @click="setTheme('dark')"><Moon :size="22" /><strong>Escuro</strong><span>Ambientes de pouca luz</span></button><button :class="{ active: theme.preference === 'system' }" @click="setTheme('system')"><Smartphone :size="22" /><strong>Sistema</strong><span>Segue o dispositivo</span></button></div>
        </article>

        <article class="settings-card">
          <header><div class="card-icon"><BellRing :size="20" /></div><div><span>NOTIFICAÇÕES</span><h3>Avisos do navegador</h3></div><StatusBadge :value="browserPermission === 'granted' ? 'success' : 'warning'" compact /></header>
          <p class="card-copy">As notificações internas funcionam sempre. O navegador precisa de permissão para exibir avisos enquanto a PWA está ativa.</p>
          <button class="button secondary" :disabled="browserPermission === 'denied' || browserPermission === 'unsupported'" @click="requestBrowserPermission"><BellRing :size="15" />{{ browserPermission === 'granted' ? 'Permissão concedida' : browserPermission === 'denied' ? 'Bloqueado no navegador' : 'Permitir notificações' }}</button>
        </article>

        <article class="settings-card">
          <header><div class="card-icon"><Smartphone :size="20" /></div><div><span>PWA</span><h3>Instalação no dispositivo</h3></div><StatusBadge :value="isStandalone ? 'success' : 'info'" compact /></header>
          <p class="card-copy">Instale a aplicação como PWA para acesso em janela própria, desktop ou celular.</p>
          <button class="button primary" :disabled="!canInstall" @click="installPwa"><Smartphone :size="15" />{{ isStandalone ? 'Aplicação já instalada' : canInstall ? 'Instalar PWA' : 'Instalação indisponível neste navegador' }}</button>
        </article>
      </section>
    </template>

    <template v-else-if="tab === 'system'">
      <section class="runtime-hero" :class="{ degraded: !runtimeHealthy }">
        <div class="runtime-icon"><CheckCircle2 v-if="runtimeHealthy" :size="26" /><AlertTriangle v-else :size="26" /></div>
        <div><span class="eyebrow">ESTADO DA STACK</span><h3>{{ runtimeHealthy ? 'Serviços essenciais operacionais' : 'Stack degradada' }}</h3><p v-if="runtime">Versão {{ runtime.version }} · verificado {{ formatDateTime(runtime.timestamp) }}</p></div>
        <StatusBadge :value="runtimeHealthy ? 'success' : 'warning'" compact />
      </section>

      <section class="runtime-grid" v-if="runtime">
        <article><Database :size="20" /><div><strong>PostgreSQL</strong><span>{{ runtime.database }}</span></div><i :class="{ ok: runtime.database === 'ok' }" /></article>
        <article><Database :size="20" /><div><strong>Redis</strong><span>{{ runtime.redis }}</span></div><i :class="{ ok: runtime.redis === 'ok' }" /></article>
        <article><Server :size="20" /><div><strong>Celery Worker</strong><span>{{ runtime.worker_online ? `${runtime.worker_count} worker(s)` : 'offline' }}</span></div><i :class="{ ok: runtime.worker_online }" /></article>
        <article><ListChecks :size="20" /><div><strong>Fila</strong><span>{{ runtime.queued_jobs }} aguardando · {{ runtime.running_jobs }} executando · {{ runtime.failed_jobs }} falha(s)</span></div><i :class="{ ok: runtime.worker_online && runtime.failed_jobs === 0 }" /></article>
      </section>

      <div v-if="runtime?.worker_error" class="runtime-error"><AlertTriangle :size="17" /><span>{{ runtime.worker_error }}</span></div>

      <section class="system-links">
        <RouterLink to="/jobs"><ListChecks :size="20" /><div><strong>Fila operacional</strong><span>Worker, jobs, retry e reconciliação</span></div></RouterLink>
        <RouterLink to="/github-tools"><Wrench :size="20" /><div><strong>GitHub Tools</strong><span>Branches, arquivos, releases, workflows e GHCR</span></div></RouterLink>
        <RouterLink to="/inactivity"><Activity :size="20" /><div><strong>Automação por inatividade</strong><span>Listas, timeout, alertar ou privar</span></div></RouterLink>
        <RouterLink v-if="auth.user?.is_superuser" to="/logs"><FileText :size="20" /><div><strong>Central de logs</strong><span>API, worker, Nginx, banco, Redis e RabbitMQ</span></div></RouterLink>
      </section>

      <section class="settings-card architecture-card">
        <header><div class="card-icon"><Link2 :size="20" /></div><div><span>ARQUITETURA DE MONITORAMENTO</span><h3>Webhooks + reconciliação periódica</h3></div></header>
        <div class="architecture-flow"><span>GitHub</span><i>→</i><span>Webhook assinado</span><i>→</i><span>API + atividade</span><i>→</i><span>RabbitMQ</span><i>→</i><span>Worker</span><i>→</i><span>Dashboard</span></div>
        <p>O webhook registra a atividade antes de enviar o job. Se o broker/worker falhar, o evento permanece salvo e aparece na Fila para retry. A reconciliação horária corrige qualquer evento eventualmente perdido sem consumir o rate limit de forma agressiva.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.settings-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:.35rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface);box-shadow:var(--shadow-sm)}.settings-tabs button{display:flex;align-items:center;justify-content:center;gap:.45rem;min-height:2.7rem;color:var(--text-muted);border:0;border-radius:.65rem;background:transparent;font-weight:750;cursor:pointer}.settings-tabs button.active{color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary) 24%,var(--border))}.required-password,.github-explain,.runtime-error{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.85rem 1rem;border:1px solid color-mix(in srgb,var(--warning) 34%,var(--border));border-radius:.85rem;background:color-mix(in srgb,var(--warning) 7%,var(--surface));color:var(--warning)}.required-password strong,.github-explain strong{color:var(--text-strong)}.required-password p,.github-explain p{margin:.1rem 0 0;color:var(--text-muted);font-size:.67rem;line-height:1.45}.github-explain{border-color:color-mix(in srgb,var(--primary) 28%,var(--border));background:color-mix(in srgb,var(--primary) 5%,var(--surface));color:var(--primary-strong)}.connection-form-panel,.connection-card,.settings-card{border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.connection-form-panel{padding:1rem}.connection-form-panel h3,.settings-card h3{margin:.08rem 0;color:var(--text-strong)}.connection-form-panel form{display:grid;grid-template-columns:1fr 1fr 2fr auto auto;align-items:end;gap:.7rem;margin-top:.8rem}.token-field>div{display:flex}.token-field>div input{border-radius:.65rem 0 0 .65rem}.token-field>div button{padding:0 .65rem;color:var(--primary-strong);border:1px solid var(--border);border-left:0;border-radius:0 .65rem .65rem 0;background:var(--surface-soft);cursor:pointer}.check-line{display:flex;align-items:center;gap:.4rem;min-height:2.7rem;color:var(--text-muted);font-size:.66rem}.permission-grid{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.8rem}.permission-grid span{padding:.25rem .45rem;border:1px solid var(--border-soft);border-radius:999px;background:var(--surface-soft);color:var(--text-muted);font-size:.56rem}.permission-grid strong{color:var(--text)}.connection-form-panel>p{margin:.6rem 0 0;color:var(--text-subtle);font-size:.59rem}.empty-connections{display:grid;place-items:center;gap:.4rem;padding:3.5rem 1rem;text-align:center;color:var(--text-muted);border:1px dashed var(--border);border-radius:1rem;background:var(--surface)}.empty-connections strong{color:var(--text-strong)}.empty-connections p{margin:0;font-size:.7rem}.connections-list{display:grid;gap:.75rem}.connection-card{padding:1rem}.connection-card>header{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem}.github-mark{display:grid;place-items:center;width:2.7rem;height:2.7rem;color:var(--primary-strong);border-radius:.8rem;background:var(--surface-soft)}.connection-title{display:grid}.connection-title strong{color:var(--text-strong)}.connection-title span{color:var(--text-muted);font-size:.63rem}.connection-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:.45rem;margin-top:.8rem}.connection-metrics div{display:grid;padding:.65rem;border:1px solid var(--border-soft);border-radius:.7rem;background:var(--surface-soft)}.connection-metrics strong{color:var(--text-strong);font-size:1rem}.connection-metrics span{color:var(--text-muted);font-size:.55rem}.connection-health{display:flex;flex-wrap:wrap;gap:.8rem;margin-top:.65rem;color:var(--text-muted);font-size:.59rem}.connection-health strong{color:var(--text)}.connection-error{display:flex;align-items:flex-start;gap:.45rem;margin-top:.65rem;padding:.55rem;color:var(--danger);border-radius:.65rem;background:color-mix(in srgb,var(--danger) 6%,var(--surface))}.connection-error.warning{color:var(--warning)}.connection-error span,.connection-error details{font-size:.6rem}.connection-error summary{cursor:pointer}.connection-error ul{max-height:120px;overflow:auto;margin:.35rem 0 0;padding-left:1rem;color:var(--text-muted)}.connection-actions{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.75rem;padding-top:.7rem;border-top:1px solid var(--border-soft)}.remote-projects{display:grid;gap:.65rem;margin-top:.8rem;padding-top:.8rem;border-top:1px solid var(--border-soft)}.remote-projects>header,.remote-projects>footer{display:flex;align-items:center;justify-content:space-between;gap:.65rem}.remote-projects>header label{display:flex;align-items:center;gap:.45rem;flex:1;max-width:620px;padding:0 .65rem;border:1px solid var(--border);border-radius:.65rem;background:var(--surface-soft)}.remote-projects>header input{width:100%;min-height:2.3rem;color:var(--text);border:0;outline:0;background:transparent}.remote-projects>header>div,.remote-projects>footer>div{display:flex;gap:.35rem}.remote-projects>footer>span{color:var(--text-muted);font-size:.62rem}.remote-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.4rem;max-height:430px;overflow:auto}.remote-list label{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.5rem;padding:.6rem;border:1px solid var(--border);border-radius:.7rem;background:var(--surface-raised);cursor:pointer}.remote-list label.selected{border-color:color-mix(in srgb,var(--primary) 38%,var(--border));background:color-mix(in srgb,var(--primary) 5%,var(--surface))}.remote-list label>div{display:grid;min-width:0}.remote-list strong,.remote-list span,.remote-list small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.remote-list strong{color:var(--text-strong);font-size:.67rem}.remote-list span{color:var(--text-muted);font-size:.56rem}.remote-list small{color:var(--text-subtle);font-size:.53rem}.remote-list em{padding:.15rem .35rem;color:var(--primary-strong);border-radius:999px;background:var(--surface-soft);font-size:.51rem;font-style:normal}.remote-loading{display:grid;gap:.35rem}.remote-loading span{height:54px}.security-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem}.settings-card{overflow:hidden;padding:1rem}.settings-card>header{display:flex;align-items:center;gap:.65rem;padding-bottom:.7rem;border-bottom:1px solid var(--border-soft)}.settings-card>header>div:nth-child(2){display:grid;flex:1}.settings-card>header span{color:var(--text-muted);font-size:.56rem;font-weight:800;letter-spacing:.08em}.card-icon{display:grid;place-items:center;width:2.5rem;height:2.5rem;color:var(--primary-strong);border-radius:.75rem;background:var(--surface-soft)}.profile-summary{display:flex;align-items:center;gap:.8rem;padding:1rem 0}.large-avatar{display:grid;place-items:center;width:4.8rem;height:4.8rem;overflow:hidden;flex:0 0 auto;color:white;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--secondary));font-size:1.3rem;font-weight:900}.large-avatar img{width:100%;height:100%;object-fit:cover}.profile-summary>div:last-child{display:grid}.profile-summary strong{color:var(--text-strong)}.profile-summary span,.profile-summary small{color:var(--text-muted);font-size:.64rem}.password-form,.security-form{display:grid;gap:.65rem;padding-top:.75rem}.card-copy{margin:.7rem 0 0;color:var(--text-muted);font-size:.66rem;line-height:1.5}.twofa-card{grid-column:1/-1}.twofa-setup{display:grid;grid-template-columns:auto 1fr 1fr;gap:1rem;align-items:start;padding-top:.8rem}.twofa-setup>img{width:170px;max-width:100%;border:1px solid var(--border);border-radius:.8rem;background:white}.twofa-main,.recovery-codes{display:grid;gap:.55rem}.twofa-main>strong,.recovery-codes>strong{color:var(--text-strong)}.secret-copy{display:flex;align-items:center;justify-content:space-between;gap:.4rem;padding:.5rem;color:var(--primary-strong);border:1px solid var(--border);border-radius:.6rem;background:var(--surface-soft);cursor:pointer}.secret-copy code{overflow:hidden;text-overflow:ellipsis}.recovery-codes{grid-template-columns:1fr 1fr}.recovery-codes>strong,.recovery-codes>.button{grid-column:1/-1}.recovery-codes code{padding:.3rem;border-radius:.4rem;background:var(--surface-soft);color:var(--text);font-size:.61rem;text-align:center}.security-state{display:flex;align-items:center;gap:.5rem;color:var(--success)}.security-state span{display:grid}.security-state strong{color:var(--text-strong)}.security-state small{color:var(--text-muted)}.sessions-card{margin-top:0}.session-list{display:grid}.session-list article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.65rem;padding:.7rem 0;border-bottom:1px solid var(--border-soft);color:var(--primary-strong)}.session-list article:last-child{border-bottom:0}.session-list article.revoked{opacity:.55}.session-list article>div{display:grid}.session-list strong{color:var(--text);font-size:.67rem}.session-list span,.session-list small{color:var(--text-muted);font-size:.57rem}.preference-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem}.theme-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.45rem;margin-top:.8rem}.theme-grid button{display:grid;justify-items:start;gap:.25rem;padding:.75rem;color:var(--text-muted);text-align:left;border:1px solid var(--border);border-radius:.75rem;background:var(--surface-soft);cursor:pointer}.theme-grid button.active{color:var(--primary-strong);border-color:color-mix(in srgb,var(--primary) 42%,var(--border));background:color-mix(in srgb,var(--primary) 6%,var(--surface))}.theme-grid strong{color:var(--text-strong);font-size:.65rem}.theme-grid span{font-size:.55rem}.runtime-hero{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.8rem;padding:1rem;border:1px solid color-mix(in srgb,var(--success) 30%,var(--border));border-radius:1rem;background:color-mix(in srgb,var(--success) 5%,var(--surface))}.runtime-hero.degraded{border-color:color-mix(in srgb,var(--warning) 36%,var(--border));background:color-mix(in srgb,var(--warning) 6%,var(--surface))}.runtime-icon{display:grid;place-items:center;width:3rem;height:3rem;color:var(--success);border-radius:.8rem;background:color-mix(in srgb,var(--success) 10%,var(--surface))}.degraded .runtime-icon{color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,var(--surface))}.runtime-hero h3{margin:.05rem 0;color:var(--text-strong)}.runtime-hero p{margin:0;color:var(--text-muted);font-size:.62rem}.runtime-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}.runtime-grid article{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.55rem;padding:.8rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface);color:var(--primary-strong)}.runtime-grid article>div{display:grid}.runtime-grid strong{color:var(--text-strong);font-size:.67rem}.runtime-grid span{color:var(--text-muted);font-size:.56rem}.runtime-grid i{width:.55rem;height:.55rem;border-radius:50%;background:var(--danger)}.runtime-grid i.ok{background:var(--success);box-shadow:0 0 0 4px color-mix(in srgb,var(--success) 9%,transparent)}.runtime-error{grid-template-columns:auto 1fr;color:var(--danger);border-color:color-mix(in srgb,var(--danger) 30%,var(--border));background:color-mix(in srgb,var(--danger) 5%,var(--surface))}.runtime-error span{font-size:.63rem}.system-links{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}.system-links a{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.6rem;padding:.85rem;color:var(--primary-strong);text-decoration:none;border:1px solid var(--border);border-radius:.8rem;background:var(--surface);box-shadow:var(--shadow-sm)}.system-links a:hover{border-color:color-mix(in srgb,var(--primary) 36%,var(--border));background:color-mix(in srgb,var(--primary) 4%,var(--surface))}.system-links div{display:grid}.system-links strong{color:var(--text-strong);font-size:.66rem}.system-links span{color:var(--text-muted);font-size:.55rem}.architecture-flow{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;margin:.8rem 0}.architecture-flow span{padding:.35rem .55rem;color:var(--primary-strong);border:1px solid var(--border);border-radius:.55rem;background:var(--surface-soft);font-size:.6rem;font-weight:800}.architecture-flow i{color:var(--text-subtle);font-style:normal}.architecture-card>p{margin:0;color:var(--text-muted);font-size:.65rem;line-height:1.5}.danger-text{color:var(--danger)!important}.full{width:100%}
@media(max-width:1150px){.connection-form-panel form{grid-template-columns:1fr 1fr}.token-field{grid-column:1/-1}.remote-list{grid-template-columns:1fr}.preference-grid{grid-template-columns:1fr 1fr}.runtime-grid,.system-links{grid-template-columns:1fr 1fr}.theme-grid{grid-template-columns:1fr 1fr 1fr}}@media(max-width:820px){.settings-tabs{grid-template-columns:1fr 1fr}.settings-tabs button{justify-content:flex-start;padding:0 .65rem}.security-layout{grid-template-columns:1fr}.twofa-card{grid-column:auto}.twofa-setup{grid-template-columns:1fr 1fr}.twofa-setup>img{grid-row:1/3}.connection-metrics{grid-template-columns:repeat(3,1fr)}.remote-projects>header,.remote-projects>footer{align-items:stretch;flex-direction:column}.remote-projects>header label{max-width:none}.remote-projects>header>div,.remote-projects>footer>div{display:grid;grid-template-columns:1fr 1fr}.remote-projects .button{width:100%}.preference-grid{grid-template-columns:1fr}.runtime-grid,.system-links{grid-template-columns:1fr 1fr}}@media(max-width:560px){.settings-tabs{grid-template-columns:1fr}.connection-form-panel form{grid-template-columns:1fr}.token-field{grid-column:auto}.connection-metrics{grid-template-columns:1fr 1fr}.connection-actions{display:grid;grid-template-columns:1fr 1fr}.connection-actions .button{width:100%}.remote-projects>header>div,.remote-projects>footer>div{grid-template-columns:1fr}.twofa-setup{grid-template-columns:1fr}.twofa-setup>img{grid-row:auto;justify-self:center}.recovery-codes{grid-template-columns:1fr}.recovery-codes>strong,.recovery-codes>.button{grid-column:auto}.theme-grid{grid-template-columns:1fr}.runtime-hero{grid-template-columns:auto 1fr}.runtime-hero>:last-child{grid-column:1/-1}.runtime-grid,.system-links{grid-template-columns:1fr}.required-password,.github-explain{grid-template-columns:auto 1fr}.github-explain>.button{grid-column:1/-1;width:100%}.session-list article{grid-template-columns:auto 1fr}.session-list .button{grid-column:1/-1;width:100%}}
</style>
