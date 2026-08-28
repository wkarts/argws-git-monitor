<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Activity, Bell, CheckCircle2, Github, KeyRound, Link2, Loader2, LockKeyhole,
  Monitor, Moon, Palette, Plus, RefreshCw, Save, ServerCog, ShieldCheck, Sun,
  Trash2, UserRound, Wrench, X
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useDialogStore } from '../stores/dialog'
import { useThemeStore, type ThemeMode } from '../stores/theme'
import { useToastStore } from '../stores/toast'
import type {
  GitHubConnection, GitHubDiagnostics, MonitoringOverview, MonitoringRuntime,
  SystemSettings, TotpSetupResponse, User
} from '../types/api'

type Section = 'account' | 'monitoring' | 'connections' | 'system'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const dialogs = useDialogStore()
const theme = useThemeStore()
const toasts = useToastStore()

const activeSection = ref<Section>('account')
const loading = ref(true)
const busy = ref('')
const connections = ref<GitHubConnection[]>([])
const diagnostics = ref<Record<string, GitHubDiagnostics>>({})
const systemSettings = ref<SystemSettings | null>(null)
const monitoringOverview = ref<MonitoringOverview | null>(null)
const monitoringRuntime = ref<MonitoringRuntime | null>(null)
const showConnectionForm = ref(false)
const editingConnectionId = ref<string | null>(null)
const totpSetup = ref<TotpSetupResponse | null>(null)
const totpCode = ref('')

const userPrefs = reactive({
  timezone: 'America/Bahia',
  locale: 'pt-BR',
  notifications: {
    browser: false,
    github: true,
    releases: true,
    workflows: true,
    backup: true,
    security: true,
  },
})
const passwordForm = reactive({ current_password: '', new_password: '', confirm_password: '' })
const connectionForm = reactive({ name: '', token: '' })
const systemForm = reactive({
  sync_interval_seconds: 3600,
  github_repository_limit: 300,
  github_request_timeout_seconds: 30,
  github_concurrency: 5,
  demo_data_enabled: false,
  notification_retention_days: 90,
})

const sections = computed(() => [
  { id: 'account' as const, label: 'Conta e aparência', icon: UserRound },
  { id: 'monitoring' as const, label: 'Monitoramento', icon: Activity },
  { id: 'connections' as const, label: 'Conexões GitHub', icon: Github },
  ...(auth.user?.is_superuser ? [{ id: 'system' as const, label: 'Sistema', icon: ServerCog }] : []),
])
const monitoringHealthy = computed(() => monitoringOverview.value?.status === 'healthy')

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error)
}
function formatInterval(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  return `${(seconds / 3600).toFixed(seconds % 3600 ? 1 : 0)} h`
}
function fillUserPreferences(): void {
  const user = auth.user
  if (!user) return
  const preferences = (user.preferences || {}) as Record<string, unknown>
  const notificationPrefs = (preferences.notifications || {}) as Record<string, unknown>
  userPrefs.timezone = user.timezone || 'America/Bahia'
  userPrefs.locale = user.locale || 'pt-BR'
  userPrefs.notifications = {
    browser: false,
    github: notificationPrefs.github !== false,
    releases: notificationPrefs.releases !== false,
    workflows: notificationPrefs.workflows !== false,
    backup: notificationPrefs.backup !== false,
    security: notificationPrefs.security !== false,
  }
}
function fillSystemForm(value: SystemSettings | null): void {
  if (!value) return
  systemForm.sync_interval_seconds = value.sync_interval_seconds
  systemForm.github_repository_limit = value.github_repository_limit
  systemForm.github_request_timeout_seconds = value.github_request_timeout_seconds
  systemForm.github_concurrency = value.github_concurrency
  systemForm.demo_data_enabled = value.demo_data_enabled
  systemForm.notification_retention_days = value.notification_retention_days
}
async function run(key: string, action: () => Promise<void>): Promise<void> {
  busy.value = key
  try { await action() }
  catch (error) { toasts.error('Operação recusada', errorMessage(error)) }
  finally { busy.value = '' }
}

async function load(): Promise<void> {
  loading.value = true
  const calls: Promise<unknown>[] = [
    api.get<GitHubConnection[]>('/github/connections'),
    api.get<MonitoringOverview>('/monitoring/overview'),
    api.get<MonitoringRuntime>('/monitoring/runtime'),
  ]
  if (auth.user?.is_superuser) calls.push(api.get<SystemSettings>('/admin/settings'))
  const results = await Promise.allSettled(calls)
  const [connectionsResult, overviewResult, runtimeResult, settingsResult] = results
  if (connectionsResult?.status === 'fulfilled') connections.value = connectionsResult.value as GitHubConnection[]
  if (overviewResult?.status === 'fulfilled') monitoringOverview.value = overviewResult.value as MonitoringOverview
  if (runtimeResult?.status === 'fulfilled') monitoringRuntime.value = runtimeResult.value as MonitoringRuntime
  if (settingsResult?.status === 'fulfilled') {
    systemSettings.value = settingsResult.value as SystemSettings
    fillSystemForm(systemSettings.value)
  }
  fillUserPreferences()
  loading.value = false
}

async function saveProfilePrefs(): Promise<void> {
  await run('profile', async () => {
    const current = auth.user
    if (!current) return
    const preferences = {
      ...(current.preferences || {}),
      notifications: {
        github: userPrefs.notifications.github,
        releases: userPrefs.notifications.releases,
        workflows: userPrefs.notifications.workflows,
        backup: userPrefs.notifications.backup,
        security: userPrefs.notifications.security,
        delivery: 'in_app',
      },
    }
    const updated = await api.patch<User>('/auth/profile', {
      timezone: userPrefs.timezone,
      locale: userPrefs.locale,
      preferences,
    })
    auth.setUser(updated)
    toasts.success('Preferências salvas', 'Alertas permanecem dentro do ARGWS Git Monitor.')
  })
}

async function changePassword(): Promise<void> {
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    toasts.warning('As senhas não conferem')
    return
  }
  if (passwordForm.new_password.length < 12) {
    toasts.warning('A nova senha precisa ter pelo menos 12 caracteres')
    return
  }
  await run('password', async () => {
    await api.post('/auth/change-password', {
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password,
    })
    Object.assign(passwordForm, { current_password: '', new_password: '', confirm_password: '' })
    await auth.refreshUser()
    toasts.success('Senha atualizada', 'Sessões antigas podem ser invalidadas por segurança.')
  })
}

async function setup2fa(): Promise<void> {
  await run('2fa-setup', async () => {
    totpSetup.value = await api.post<TotpSetupResponse>('/auth/2fa/setup')
    totpCode.value = ''
  })
}
async function confirm2fa(): Promise<void> {
  if (!totpSetup.value || totpCode.value.length !== 6) return
  await run('2fa-confirm', async () => {
    await api.post('/auth/2fa/confirm', { code: totpCode.value })
    totpSetup.value = null
    totpCode.value = ''
    await auth.refreshUser()
    toasts.success('2FA ativado', 'Sua conta agora exige o segundo fator.')
  })
}
async function disable2fa(): Promise<void> {
  if (totpCode.value.length !== 6) {
    toasts.warning('Informe um código atual de 6 dígitos')
    return
  }
  const accepted = await dialogs.askConfirmation({
    title: 'Desativar autenticação em dois fatores?',
    message: 'Sua conta perderá uma camada importante de proteção. Esta alteração exige um código válido do autenticador.',
    tone: 'danger',
    confirmLabel: 'Desativar 2FA',
  })
  if (!accepted) return
  await run('2fa-disable', async () => {
    await api.post('/auth/2fa/disable', { code: totpCode.value })
    totpCode.value = ''
    await auth.refreshUser()
    toasts.success('2FA desativado')
  })
}

function resetConnectionForm(): void {
  editingConnectionId.value = null
  connectionForm.name = ''
  connectionForm.token = ''
  showConnectionForm.value = false
}
function editConnection(connection: GitHubConnection): void {
  editingConnectionId.value = connection.id
  connectionForm.name = connection.name
  connectionForm.token = ''
  showConnectionForm.value = true
}
async function saveConnection(): Promise<void> {
  const name = connectionForm.name.trim()
  if (!name) { toasts.warning('Informe um nome para a conexão'); return }
  if (!editingConnectionId.value && !connectionForm.token.trim()) {
    toasts.warning('Informe o token GitHub')
    return
  }
  await run('connection-save', async () => {
    if (editingConnectionId.value) {
      await api.patch(`/github/connections/${editingConnectionId.value}`, {
        name,
        ...(connectionForm.token.trim() ? { token: connectionForm.token.trim() } : {}),
      })
      toasts.success('Conexão atualizada')
    } else {
      await api.post('/github/connections', { name, token: connectionForm.token.trim() })
      toasts.success('Conexão adicionada')
    }
    resetConnectionForm()
    await load()
  })
}
async function removeConnection(connection: GitHubConnection): Promise<void> {
  const accepted = await dialogs.askConfirmation({
    title: 'Remover conexão GitHub?',
    message: `A conexão “${connection.name}” (@${connection.github_login || 'GitHub'}) será removida do Git Monitor. Repositórios no GitHub não são excluídos por esta operação.`,
    tone: 'danger',
    confirmLabel: 'Remover conexão',
  })
  if (!accepted) return
  await run(`connection-delete-${connection.id}`, async () => {
    await api.delete(`/github/connections/${connection.id}`)
    delete diagnostics.value[connection.id]
    toasts.success('Conexão removida')
    await load()
  })
}
async function testConnection(connection: GitHubConnection): Promise<void> {
  await run(`connection-test-${connection.id}`, async () => {
    diagnostics.value[connection.id] = await api.get<GitHubDiagnostics>(`/github/connections/${connection.id}/diagnostics`)
    const data = diagnostics.value[connection.id]
    data.status === 'healthy'
      ? toasts.success('Conexão saudável', `@${data.github_login} · ${data.visible_repository_count} repositório(s) visível(is).`)
      : toasts.warning('Conexão requer atenção', data.errors.join(' · ') || 'Consulte o diagnóstico abaixo.')
  })
}
async function syncConnection(connection: GitHubConnection): Promise<void> {
  await run(`connection-sync-${connection.id}`, async () => {
    await api.post(`/github/connections/${connection.id}/sync`)
    toasts.success('Reconciliação solicitada', 'Webhooks continuam sendo o caminho principal do realtime.')
  })
}
async function repairWebhooks(connection: GitHubConnection): Promise<void> {
  await run(`webhooks-${connection.id}`, async () => {
    const result = await api.post<{ message?: string }>(`/github/connections/${connection.id}/webhooks/reconcile`, {})
    toasts.success('Webhooks reconciliados', result.message || 'Assinaturas atualizadas no GitHub.')
    await testConnection(connection)
  })
}

async function refreshMonitoring(): Promise<void> {
  await run('monitoring-refresh', async () => {
    ;[monitoringOverview.value, monitoringRuntime.value] = await Promise.all([
      api.get<MonitoringOverview>('/monitoring/overview'),
      api.get<MonitoringRuntime>('/monitoring/runtime'),
    ])
  })
}
async function reconcileNow(): Promise<void> {
  await run('monitoring-reconcile', async () => {
    await Promise.all(connections.value.map((connection) => api.post(`/github/connections/${connection.id}/sync`)))
    toasts.success('Reconciliação enviada', `${connections.value.length} conexão(ões) agendada(s).`)
  })
}

async function saveSystemSettings(): Promise<void> {
  if (!auth.user?.is_superuser) return
  await run('system-save', async () => {
    systemSettings.value = await api.patch<SystemSettings>('/admin/settings', { ...systemForm })
    fillSystemForm(systemSettings.value)
    toasts.success('Configurações do sistema salvas')
  })
}

watch(() => auth.user, fillUserPreferences)
watch(() => route.query.password, (value) => {
  if (value === 'required') activeSection.value = 'account'
}, { immediate: true })

onMounted(async () => {
  await load()
  if (route.query.password === 'required') {
    activeSection.value = 'account'
    void router.replace({ query: { ...route.query, password: undefined } })
  }
})
</script>

<template>
  <div class="settings-page page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">PREFERÊNCIAS E CONTROLE</span>
        <h2>Configurações</h2>
        <p>Conta, segurança, monitoramento e integrações em uma área única, sem caixas de diálogo ou notificações do navegador.</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
    </section>

    <nav class="settings-tabs">
      <button v-for="item in sections" :key="item.id" :class="{active:activeSection===item.id}" @click="activeSection=item.id">
        <component :is="item.icon" :size="16"/>{{item.label}}
      </button>
    </nav>

    <template v-if="activeSection==='account'">
      <section class="settings-grid two">
        <article class="settings-card">
          <header><div class="card-icon"><Palette :size="19"/></div><div><strong>Aparência</strong><span>Tema da interface</span></div></header>
          <div class="theme-options">
            <button :class="{active:theme.mode==='light'}" @click="theme.setMode('light' as ThemeMode)"><Sun :size="18"/><span>Claro</span></button>
            <button :class="{active:theme.mode==='dark'}" @click="theme.setMode('dark' as ThemeMode)"><Moon :size="18"/><span>Escuro</span></button>
            <button :class="{active:theme.mode==='system'}" @click="theme.setMode('system' as ThemeMode)"><Monitor :size="18"/><span>Sistema</span></button>
          </div>
        </article>

        <article class="settings-card">
          <header><div class="card-icon"><Bell :size="19"/></div><div><strong>Alertas internos</strong><span>Mensagens do próprio Git Monitor</span></div></header>
          <div class="platform-message">
            <ShieldCheck :size="18"/>
            <p>O Git Monitor não pede permissão ao Chrome/Windows. Eventos aparecem na Central de Alertas, contadores, toasts e dialogs internos da plataforma.</p>
          </div>
          <div class="preference-list">
            <label><input v-model="userPrefs.notifications.github" type="checkbox"/><span>Eventos GitHub</span></label>
            <label><input v-model="userPrefs.notifications.releases" type="checkbox"/><span>Releases</span></label>
            <label><input v-model="userPrefs.notifications.workflows" type="checkbox"/><span>GitHub Actions</span></label>
            <label><input v-model="userPrefs.notifications.backup" type="checkbox"/><span>Backup & Recovery</span></label>
            <label><input v-model="userPrefs.notifications.security" type="checkbox"/><span>Segurança</span></label>
          </div>
        </article>
      </section>

      <section class="settings-card">
        <header><div class="card-icon"><UserRound :size="19"/></div><div><strong>Preferências da conta</strong><span>Fuso horário e idioma</span></div></header>
        <div class="form-grid two">
          <label class="field"><span>Fuso horário</span><select v-model="userPrefs.timezone"><option value="America/Bahia">America/Bahia</option><option value="America/Sao_Paulo">America/Sao_Paulo</option><option value="UTC">UTC</option></select></label>
          <label class="field"><span>Idioma</span><select v-model="userPrefs.locale"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English (US)</option></select></label>
        </div>
        <footer><button class="button primary" :disabled="busy==='profile'" @click="saveProfilePrefs"><Save :size="15"/>Salvar preferências</button></footer>
      </section>

      <section class="settings-grid two">
        <article class="settings-card">
          <header><div class="card-icon"><KeyRound :size="19"/></div><div><strong>Alterar senha</strong><span>Mínimo de 12 caracteres</span></div></header>
          <div class="form-stack">
            <label class="field"><span>Senha atual</span><input v-model="passwordForm.current_password" type="password" autocomplete="current-password"/></label>
            <label class="field"><span>Nova senha</span><input v-model="passwordForm.new_password" type="password" autocomplete="new-password"/></label>
            <label class="field"><span>Confirmar nova senha</span><input v-model="passwordForm.confirm_password" type="password" autocomplete="new-password"/></label>
          </div>
          <footer><button class="button primary" :disabled="busy==='password'" @click="changePassword"><LockKeyhole :size="15"/>Atualizar senha</button></footer>
        </article>

        <article class="settings-card">
          <header><div class="card-icon"><ShieldCheck :size="19"/></div><div><strong>Autenticação em dois fatores</strong><span>{{auth.user?.totp_enabled?'Proteção ativa':'Proteção disponível'}}</span></div></header>
          <template v-if="!auth.user?.totp_enabled">
            <div v-if="!totpSetup" class="twofa-state"><CheckCircle2 :size="20"/><p>Use um aplicativo autenticador compatível com TOTP.</p><button class="button secondary" :disabled="busy==='2fa-setup'" @click="setup2fa">Configurar 2FA</button></div>
            <div v-else class="twofa-setup"><div class="secret-box"><span>Secret</span><code>{{totpSetup.secret}}</code></div><p>Cadastre pelo URI ou secret e informe o primeiro código válido.</p><label class="field"><span>Código de 6 dígitos</span><input v-model="totpCode" inputmode="numeric" maxlength="6"/></label><button class="button primary" :disabled="busy==='2fa-confirm'||totpCode.length!==6" @click="confirm2fa">Confirmar 2FA</button></div>
          </template>
          <div v-else class="twofa-state active"><CheckCircle2 :size="20"/><p>O segundo fator está habilitado para esta conta.</p><label class="field"><span>Código atual</span><input v-model="totpCode" inputmode="numeric" maxlength="6"/></label><button class="button danger-soft" :disabled="busy==='2fa-disable'||totpCode.length!==6" @click="disable2fa">Desativar 2FA</button></div>
        </article>
      </section>
    </template>

    <template v-else-if="activeSection==='monitoring'">
      <section class="monitor-hero" :class="{healthy:monitoringHealthy}">
        <div><Activity :size="22"/><span><strong>{{monitoringHealthy?'Monitoramento operacional':'Monitoramento requer atenção'}}</strong><small>Webhook + materialização + Redis/WebSocket são o caminho principal; reconciliação REST é fallback.</small></span></div>
        <button class="button secondary" :disabled="busy==='monitoring-refresh'" @click="refreshMonitoring"><RefreshCw :size="15"/>Atualizar estado</button>
      </section>
      <section class="metric-grid">
        <article><span>Repositórios</span><strong>{{monitoringOverview?.repositories.monitored??0}}</strong><small>{{monitoringOverview?.repositories.total??0}} conhecidos</small></article>
        <article><span>WebSocket</span><strong>{{monitoringRuntime?.websocket.status||'—'}}</strong><small>{{monitoringRuntime?.websocket.clients??0}} cliente(s)</small></article>
        <article><span>Worker</span><strong>{{monitoringRuntime?.worker.status||'—'}}</strong><small>{{monitoringRuntime?.worker.count??0}} processo(s)</small></article>
        <article><span>Reconciliação</span><strong>{{formatInterval(monitoringOverview?.configuration.reconciliation_interval_seconds)}}</strong><small>fallback de consistência</small></article>
      </section>
      <section class="settings-card">
        <header><div class="card-icon"><Wrench :size="19"/></div><div><strong>Ações operacionais</strong><span>Use apenas para recuperar divergência ou evento perdido</span></div></header>
        <div class="action-row"><button class="button secondary" :disabled="busy==='monitoring-reconcile'||!connections.length" @click="reconcileNow"><RefreshCw :size="15"/>Reconciliar todas as conexões</button></div>
      </section>
    </template>

    <template v-else-if="activeSection==='connections'">
      <section class="section-heading"><div><h3>Conexões GitHub</h3><p>Tokens ficam criptografados no backend e nunca são reenviados ao frontend.</p></div><button class="button primary" @click="showConnectionForm=true; editingConnectionId=null; connectionForm.name=''; connectionForm.token='' "><Plus :size="15"/>Nova conexão</button></section>

      <section v-if="showConnectionForm" class="settings-card connection-editor">
        <header><div class="card-icon"><Github :size="19"/></div><div><strong>{{editingConnectionId?'Editar conexão':'Adicionar conexão'}}</strong><span>{{editingConnectionId?'Deixe o token vazio para manter a credencial atual.':'Use um token com os escopos necessários aos repositórios monitorados.'}}</span></div><button class="icon-button" @click="resetConnectionForm"><X :size="16"/></button></header>
        <div class="form-grid two"><label class="field"><span>Nome</span><input v-model="connectionForm.name" placeholder="GitHub principal"/></label><label class="field"><span>Token</span><input v-model="connectionForm.token" type="password" autocomplete="off" placeholder="ghp_... / github_pat_..."/></label></div>
        <footer><button class="button primary" :disabled="busy==='connection-save'" @click="saveConnection"><Save :size="15"/>Salvar conexão</button></footer>
      </section>

      <section class="connection-list">
        <article v-for="connection in connections" :key="connection.id" class="connection-card">
          <header><div class="connection-identity"><div class="github-icon"><Github :size="20"/></div><div><strong>{{connection.name}}</strong><span>@{{connection.github_login||'não identificado'}} · {{connection.status}}</span></div></div><span class="state-dot" :class="connection.status"/></header>
          <div class="connection-meta"><span><b>{{connection.repository_count??0}}</b> repositórios</span><span>Último sync <b>{{connection.last_sync_at?new Date(connection.last_sync_at).toLocaleString('pt-BR'):'—'}}</b></span></div>
          <div class="connection-actions"><button class="button ghost compact" @click="editConnection(connection)">Editar</button><button class="button ghost compact" :disabled="busy===`connection-test-${connection.id}`" @click="testConnection(connection)"><ShieldCheck :size="13"/>Diagnóstico</button><button class="button ghost compact" :disabled="busy===`webhooks-${connection.id}`" @click="repairWebhooks(connection)"><Link2 :size="13"/>Webhooks</button><button class="button secondary compact" :disabled="busy===`connection-sync-${connection.id}`" @click="syncConnection(connection)"><RefreshCw :size="13"/>Reconciliar</button><button class="button ghost compact danger-text" @click="removeConnection(connection)"><Trash2 :size="13"/>Remover</button></div>
          <div v-if="diagnostics[connection.id]" class="diagnostic-box" :class="diagnostics[connection.id].status"><strong>{{diagnostics[connection.id].status}}</strong><span>{{diagnostics[connection.id].visible_repository_count}} repositório(s) visível(is) · webhook {{diagnostics[connection.id].webhook.status}}</span><small v-if="diagnostics[connection.id].errors.length">{{diagnostics[connection.id].errors.join(' · ')}}</small></div>
        </article>
        <div v-if="!connections.length&&!loading" class="empty-state">Nenhuma conexão GitHub configurada.</div>
      </section>
    </template>

    <template v-else-if="activeSection==='system'&&auth.user?.is_superuser">
      <section class="settings-card">
        <header><div class="card-icon"><ServerCog :size="19"/></div><div><strong>Parâmetros do sistema</strong><span>Configurações persistidas administrativamente</span></div></header>
        <div class="form-grid three">
          <label class="field"><span>Reconciliação (segundos)</span><input v-model.number="systemForm.sync_interval_seconds" type="number" min="60"/></label>
          <label class="field"><span>Limite de repositórios</span><input v-model.number="systemForm.github_repository_limit" type="number" min="1"/></label>
          <label class="field"><span>Timeout GitHub (s)</span><input v-model.number="systemForm.github_request_timeout_seconds" type="number" min="1"/></label>
          <label class="field"><span>Concorrência GitHub</span><input v-model.number="systemForm.github_concurrency" type="number" min="1" max="32"/></label>
          <label class="field"><span>Retenção de alertas (dias)</span><input v-model.number="systemForm.notification_retention_days" type="number" min="1"/></label>
          <label class="switch-line"><input v-model="systemForm.demo_data_enabled" type="checkbox"/><span>Dados de demonstração</span></label>
        </div>
        <footer><button class="button primary" :disabled="busy==='system-save'" @click="saveSystemSettings"><Save :size="15"/>Salvar sistema</button></footer>
      </section>
      <section v-if="systemSettings" class="system-facts">
        <article><span>Versão</span><strong>v{{systemSettings.app_version}}</strong></article>
        <article><span>Ambiente</span><strong>{{systemSettings.app_env}}</strong></article>
        <article><span>Timezone</span><strong>{{systemSettings.timezone}}</strong></article>
        <article><span>API</span><strong>{{systemSettings.public_base_url}}</strong></article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.settings-page{gap:1rem}.settings-tabs{display:flex;gap:.3rem;overflow-x:auto;padding:.35rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface)}.settings-tabs button{display:inline-flex;align-items:center;gap:.4rem;flex:0 0 auto;min-height:2.35rem;padding:.45rem .7rem;color:var(--text-muted);border:0;border-radius:.65rem;background:transparent;font:750 .68rem inherit;cursor:pointer}.settings-tabs button.active{color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface));box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--primary) 25%,var(--border))}.settings-grid{display:grid;gap:1rem}.settings-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.settings-card{display:grid;gap:.9rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.settings-card>header{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem}.card-icon,.github-icon{display:grid;place-items:center;width:2.45rem;height:2.45rem;border-radius:.75rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.settings-card header>div:nth-child(2){display:grid}.settings-card header strong{color:var(--text-strong);font-size:.78rem}.settings-card header span{color:var(--text-muted);font-size:.62rem}.settings-card footer{display:flex;justify-content:flex-end;padding-top:.65rem;border-top:1px solid var(--border-soft)}.theme-options{display:grid;grid-template-columns:repeat(3,1fr);gap:.55rem}.theme-options button{display:grid;place-items:center;gap:.35rem;min-height:5rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised);cursor:pointer}.theme-options button.active{color:var(--primary-strong);border-color:var(--primary);background:color-mix(in srgb,var(--primary) 7%,var(--surface))}.platform-message{display:flex;align-items:flex-start;gap:.6rem;padding:.7rem;color:var(--success);border:1px solid color-mix(in srgb,var(--success) 25%,var(--border));border-radius:.75rem;background:color-mix(in srgb,var(--success) 5%,var(--surface))}.platform-message p{margin:0;color:var(--text-muted);font-size:.65rem;line-height:1.5}.preference-list{display:grid;grid-template-columns:repeat(2,1fr);gap:.45rem}.preference-list label,.switch-line{display:flex;align-items:center;gap:.45rem;min-height:2.4rem;padding:.45rem .55rem;color:var(--text);border:1px solid var(--border-soft);border-radius:.65rem;background:var(--surface-raised);font-size:.65rem}.form-grid{display:grid;gap:.7rem}.form-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.form-stack{display:grid;gap:.65rem}.field{display:grid;gap:.3rem}.field>span{color:var(--text-strong);font-size:.61rem;font-weight:800}.field input,.field select{width:100%;min-height:2.55rem;padding:.5rem .65rem;color:var(--text);border:1px solid var(--border);border-radius:.68rem;background:var(--surface-raised);font:inherit;font-size:.7rem}.twofa-state,.twofa-setup{display:grid;gap:.65rem;align-content:start}.twofa-state>svg{color:var(--primary-strong)}.twofa-state.active>svg{color:var(--success)}.twofa-state p,.twofa-setup p{margin:0;color:var(--text-muted);font-size:.66rem;line-height:1.5}.secret-box{display:grid;gap:.2rem;padding:.65rem;border:1px solid var(--border-soft);border-radius:.7rem;background:var(--surface-raised)}.secret-box span{color:var(--text-muted);font-size:.58rem}.secret-box code{overflow-wrap:anywhere;color:var(--text-strong);font-size:.66rem}.danger-soft{min-height:2.4rem;padding:.5rem .8rem;color:var(--danger);border:1px solid color-mix(in srgb,var(--danger) 30%,var(--border));border-radius:.65rem;background:color-mix(in srgb,var(--danger) 5%,var(--surface));font-weight:800;cursor:pointer}.monitor-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem;border:1px solid color-mix(in srgb,var(--warning) 35%,var(--border));border-radius:1rem;background:color-mix(in srgb,var(--warning) 5%,var(--surface))}.monitor-hero.healthy{border-color:color-mix(in srgb,var(--success) 30%,var(--border));background:color-mix(in srgb,var(--success) 5%,var(--surface))}.monitor-hero>div{display:flex;align-items:center;gap:.7rem;color:var(--warning)}.monitor-hero.healthy>div{color:var(--success)}.monitor-hero span{display:grid}.monitor-hero strong{color:var(--text-strong)}.monitor-hero small{color:var(--text-muted);font-size:.62rem}.metric-grid,.system-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem}.metric-grid article,.system-facts article{display:grid;gap:.22rem;padding:.85rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface)}.metric-grid span,.system-facts span{color:var(--text-muted);font-size:.58rem}.metric-grid strong,.system-facts strong{overflow:hidden;color:var(--text-strong);font-size:1rem;text-overflow:ellipsis}.metric-grid small{color:var(--text-subtle);font-size:.55rem}.action-row{display:flex;gap:.55rem}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.section-heading h3{margin:0;color:var(--text-strong)}.section-heading p{margin:.15rem 0 0;color:var(--text-muted);font-size:.66rem}.connection-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem}.connection-card{display:grid;gap:.7rem;padding:.9rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface);box-shadow:var(--shadow-sm)}.connection-card>header{display:flex;align-items:center;justify-content:space-between}.connection-identity{display:flex;align-items:center;gap:.6rem}.connection-identity>div:last-child{display:grid}.connection-identity strong{color:var(--text-strong);font-size:.72rem}.connection-identity span{color:var(--text-muted);font-size:.6rem}.state-dot{width:.55rem;height:.55rem;border-radius:50%;background:var(--warning)}.state-dot.active,.state-dot.healthy{background:var(--success);box-shadow:0 0 7px var(--success)}.connection-meta{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}.connection-meta span{display:grid;padding:.5rem;color:var(--text-muted);border-radius:.6rem;background:var(--surface-raised);font-size:.56rem}.connection-meta b{color:var(--text-strong)}.connection-actions{display:flex;flex-wrap:wrap;gap:.35rem}.diagnostic-box{display:grid;gap:.15rem;padding:.55rem;border:1px solid var(--border-soft);border-radius:.65rem;background:var(--surface-raised)}.diagnostic-box.healthy{border-color:color-mix(in srgb,var(--success) 25%,var(--border))}.diagnostic-box strong{color:var(--text-strong);font-size:.62rem}.diagnostic-box span,.diagnostic-box small{color:var(--text-muted);font-size:.56rem}.empty-state{grid-column:1/-1;padding:2rem;color:var(--text-muted);text-align:center}.danger-text{color:var(--danger)!important}.icon-button{display:grid;place-items:center;width:2rem;height:2rem;padding:0;color:var(--text-muted);border:1px solid var(--border);border-radius:.6rem;background:var(--surface-raised);cursor:pointer}
@media(max-width:1050px){.settings-grid.two,.connection-list{grid-template-columns:1fr}.form-grid.three,.metric-grid,.system-facts{grid-template-columns:repeat(2,1fr)}}@media(max-width:650px){.form-grid.two,.form-grid.three,.metric-grid,.system-facts,.preference-list{grid-template-columns:1fr}.theme-options{grid-template-columns:repeat(3,1fr)}.monitor-hero,.section-heading{align-items:stretch;flex-direction:column}.monitor-hero .button,.section-heading .button{width:100%}.connection-meta{grid-template-columns:1fr}.connection-actions{display:grid;grid-template-columns:1fr 1fr}.connection-actions .button{width:100%}.settings-card footer .button{width:100%}}
</style>
