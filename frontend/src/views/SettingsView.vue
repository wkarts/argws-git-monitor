<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  BellRing,
  Check,
  ChevronDown,
  ChevronUp,
  Database,
  Download,
  Eye,
  EyeOff,
  Github,
  KeyRound,
  Link2,
  LockKeyhole,
  Moon,
  Plus,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  Smartphone,
  Sun,
  Trash2,
  Webhook
} from 'lucide-vue-next'
import StatusBadge from '../components/StatusBadge.vue'
import { usePwaInstall } from '../composables/usePwaInstall'
import { ApiError, api } from '../services/api'
import { formatDateTime } from '../services/format'
import { useAuthStore } from '../stores/auth'
import { useThemeStore, type ThemePreference } from '../stores/theme'
import { useToastStore } from '../stores/toast'
import type {
  GitHubConnection,
  MessageResponse,
  RemoteRepository,
  SyncResponse,
  WebhookConfigureResult
} from '../types/api'

const auth = useAuthStore()
const appVersion = String(import.meta.env.VITE_APP_VERSION || '0.2.0')
const theme = useThemeStore()
const toasts = useToastStore()
const route = useRoute()
const router = useRouter()
const { canInstall, isStandalone, install } = usePwaInstall()

const connections = ref<GitHubConnection[]>([])
const loading = ref(true)
const showConnectionForm = ref(false)
const showToken = ref(false)
const savingConnection = ref(false)
const activeConnectionId = ref<string | null>(null)
const remoteLoadingId = ref<string | null>(null)
const remoteRepositories = reactive<Record<string, RemoteRepository[]>>({})
const connectionForm = reactive({
  name: 'GitHub principal',
  token: '',
  auto_import: true,
  api_url: 'https://api.github.com'
})
const passwordForm = reactive({ current: '', next: '', confirmation: '' })
const changingPassword = ref(false)
const browserPermission = ref<'default' | 'denied' | 'granted' | 'unsupported'>(
  'Notification' in window ? Notification.permission : 'unsupported'
)
const mustChangePassword = computed(() => auth.user?.must_change_password || route.query.password === 'required')
const realConnections = computed(() => connections.value.filter((item) => item.status !== 'demo'))

async function loadConnections(): Promise<void> {
  loading.value = true
  try {
    connections.value = await api.get<GitHubConnection[]>('/github/connections')
    if (!realConnections.value.length) showConnectionForm.value = true
  } catch (error) {
    toasts.error('Falha ao carregar conexões', error instanceof ApiError ? error.message : undefined)
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
    toasts.success('GitHub conectado', `Conta ${created.github_login} validada. A sincronização foi iniciada.`)
    await loadConnections()
  } catch (error) {
    toasts.error('Não foi possível conectar', error instanceof ApiError ? error.message : undefined)
  } finally {
    savingConnection.value = false
  }
}

async function syncConnection(connection: GitHubConnection): Promise<void> {
  try {
    const result = await api.post<SyncResponse>(`/github/connections/${connection.id}/sync`)
    toasts.success('Sincronização enfileirada', result.message)
  } catch (error) {
    toasts.error('Falha ao sincronizar', error instanceof ApiError ? error.message : undefined)
  }
}

async function removeConnection(connection: GitHubConnection): Promise<void> {
  if (!window.confirm(`Remover a conexão “${connection.name}” e os dados monitorados dela?`)) return
  try {
    const result = await api.delete<MessageResponse>(`/github/connections/${connection.id}`)
    toasts.success('Conexão removida', result.message)
    delete remoteRepositories[connection.id]
    await loadConnections()
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
    toasts.error('Falha ao consultar o GitHub', error instanceof ApiError ? error.message : undefined)
  } finally {
    remoteLoadingId.value = null
  }
}

function selectedRemote(connectionId: string): number[] {
  return (remoteRepositories[connectionId] || [])
    .filter((item) => item.selected)
    .map((item) => item.github_id)
}

async function importSelected(connection: GitHubConnection): Promise<void> {
  const ids = selectedRemote(connection.id)
  if (!ids.length) {
    toasts.info('Selecione repositórios', 'Marque pelo menos um item na lista.')
    return
  }
  try {
    const result = await api.post<SyncResponse>(`/github/connections/${connection.id}/import`, {
      repository_ids: ids
    })
    toasts.success('Importação iniciada', result.message)
  } catch (error) {
    toasts.error('Falha ao importar', error instanceof ApiError ? error.message : undefined)
  }
}

async function configureWebhooks(connection: GitHubConnection): Promise<void> {
  if (!window.confirm('Criar webhooks nos repositórios monitorados? O token precisa da permissão Webhooks: escrita.')) return
  try {
    const results = await api.post<WebhookConfigureResult[]>(
      `/github/connections/${connection.id}/configure-webhooks`,
      {}
    )
    const success = results.filter((item) => item.success).length
    const failed = results.length - success
    if (failed) toasts.warning(`${success} webhook(s) configurado(s)`, `${failed} falharam por permissão ou duplicidade.`)
    else toasts.success('Webhooks configurados', `${success} repositório(s) atualizado(s).`)
  } catch (error) {
    toasts.error('Falha ao configurar webhooks', error instanceof ApiError ? error.message : undefined)
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

async function requestBrowserPermission(): Promise<void> {
  if (!('Notification' in window)) return
  browserPermission.value = await Notification.requestPermission()
  if (browserPermission.value === 'granted') {
    new Notification('ARGWS Git Monitor', { body: 'Avisos do navegador autorizados.', icon: '/pwa-192x192.png' })
  }
}

async function installPwa(): Promise<void> {
  const installed = await install()
  if (installed) toasts.success('Aplicação instalada', 'O Git Monitor foi adicionado ao dispositivo.')
}

function setTheme(value: ThemePreference): void {
  theme.setPreference(value)
}

onMounted(loadConnections)
</script>

<template>
  <div class="page-stack settings-page">
    <section class="page-heading">
      <div><span class="eyebrow">CONFIGURAÇÃO E SEGURANÇA</span><h2>Configurações</h2><p>Gerencie a conta, integrações GitHub, PWA, aparência e automações.</p></div>
      <button class="button primary" @click="showConnectionForm = !showConnectionForm"><Plus :size="17" />Nova conexão</button>
    </section>

    <section v-if="mustChangePassword" class="required-password"><AlertTriangle :size="20" /><div><strong>Troca de senha obrigatória</strong><p>A senha inicial é temporária. Altere-a para liberar o restante da aplicação.</p></div></section>

    <section class="settings-grid">
      <article class="settings-card account-card">
        <header><div class="card-icon"><ShieldCheck :size="20" /></div><div><span>CONTA LOCAL</span><h3>Segurança de acesso</h3></div></header>
        <div class="account-summary"><div class="large-avatar">{{ auth.user?.name?.slice(0, 1).toUpperCase() }}</div><div><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span><small>{{ auth.user?.is_superuser ? 'Administrador da plataforma' : 'Usuário' }}</small></div></div>
        <form class="password-form" @submit.prevent="changePassword">
          <label class="field"><span>Senha atual</span><input v-model="passwordForm.current" type="password" autocomplete="current-password" required /></label>
          <label class="field"><span>Nova senha</span><input v-model="passwordForm.next" type="password" autocomplete="new-password" minlength="12" required /></label>
          <label class="field"><span>Confirmar nova senha</span><input v-model="passwordForm.confirmation" type="password" autocomplete="new-password" minlength="12" required /></label>
          <button class="button secondary full" :disabled="changingPassword"><KeyRound :size="16" />{{ changingPassword ? 'Alterando…' : 'Alterar senha e sair' }}</button>
        </form>
      </article>

      <article class="settings-card preferences-card">
        <header><div class="card-icon"><Smartphone :size="20" /></div><div><span>DISPOSITIVO</span><h3>PWA e preferências</h3></div></header>
        <div class="setting-row"><div><strong>Instalação como aplicativo</strong><span>{{ isStandalone ? 'Esta PWA já está instalada neste dispositivo.' : 'Adicione um ícone e abra em tela cheia.' }}</span></div><button class="button secondary small" :disabled="!canInstall || isStandalone" @click="installPwa"><Download :size="15" />{{ isStandalone ? 'Instalada' : 'Instalar' }}</button></div>
        <div class="setting-row"><div><strong>Avisos do navegador</strong><span>Permissão atual: {{ browserPermission }}</span></div><button class="button secondary small" :disabled="browserPermission === 'granted' || browserPermission === 'unsupported'" @click="requestBrowserPermission"><BellRing :size="15" />{{ browserPermission === 'granted' ? 'Permitidos' : 'Permitir' }}</button></div>
        <div class="theme-setting"><strong>Aparência</strong><div class="theme-options"><button :class="{ active: theme.preference === 'dark' }" @click="setTheme('dark')"><Moon :size="16" />Escuro</button><button :class="{ active: theme.preference === 'light' }" @click="setTheme('light')"><Sun :size="16" />Claro</button><button :class="{ active: theme.preference === 'system' }" @click="setTheme('system')"><Smartphone :size="16" />Sistema</button></div></div>
        <div class="security-info"><LockKeyhole :size="17" /><p>Tokens GitHub são criptografados no backend e nunca retornam para o navegador depois do cadastro.</p></div>
      </article>
    </section>

    <section class="github-section">
      <div class="section-heading"><div><span>INTEGRAÇÕES</span><h3>Contas GitHub</h3><p>Use token granular ou token compatível com GitHub Enterprise Server.</p></div><StatusBadge :value="realConnections.length ? 'success' : 'unknown'" /></div>

      <form v-if="showConnectionForm" class="connection-form" @submit.prevent="createConnection">
        <header><Github :size="22" /><div><strong>Conectar uma conta GitHub</strong><span>O token será validado no GitHub antes de ser criptografado.</span></div></header>
        <div class="form-grid">
          <label class="field"><span>Nome da conexão</span><input v-model="connectionForm.name" type="text" maxlength="120" required /></label>
          <label class="field"><span>URL da API</span><input v-model="connectionForm.api_url" type="url" required /></label>
          <label class="field full-field"><span>Token de acesso</span><div class="input-with-icon"><KeyRound :size="17" /><input v-model="connectionForm.token" :type="showToken ? 'text' : 'password'" autocomplete="off" placeholder="github_pat_…" required /><button type="button" class="input-action" @click="showToken = !showToken"><EyeOff v-if="showToken" :size="16" /><Eye v-else :size="16" /></button></div></label>
        </div>
        <label class="check-row"><input v-model="connectionForm.auto_import" type="checkbox" /><span><strong>Importar e sincronizar automaticamente</strong><small>Busca todos os repositórios que o token pode acessar.</small></span></label>
        <div class="permission-box"><ShieldCheck :size="18" /><div><strong>Permissões recomendadas</strong><p>Metadata: leitura; Contents: leitura; Actions: leitura; Pull requests: leitura; Issues: leitura. Para os botões de reexecução, conceda Actions: escrita. Para instalação automática de webhooks, conceda Webhooks: escrita.</p></div></div>
        <footer><button type="button" class="button ghost" @click="showConnectionForm = false">Cancelar</button><button class="button primary" :disabled="savingConnection"><Link2 :size="16" />{{ savingConnection ? 'Validando…' : 'Validar e conectar' }}</button></footer>
      </form>

      <div v-if="loading" class="connection-list"><div v-for="index in 2" :key="index" class="skeleton connection-skeleton" /></div>
      <div v-else class="connection-list">
        <article v-for="connection in connections" :key="connection.id" class="connection-card" :class="`status-${connection.status}`">
          <div class="connection-main">
            <div class="github-avatar"><Github :size="21" /></div>
            <div class="connection-copy"><div><strong>{{ connection.name }}</strong><StatusBadge :value="connection.status === 'active' ? 'success' : connection.status === 'demo' ? 'unknown' : 'failure'" compact /></div><span>@{{ connection.github_login }} · token final {{ connection.token_last_four || 'demo' }}</span><small>{{ connection.repository_count }} repositório(s) · última sincronização {{ formatDateTime(connection.last_sync_at) }}</small></div>
            <div class="rate-info"><Database :size="15" /><span>API restante</span><strong>{{ connection.rate_limit_remaining ?? '—' }}</strong></div>
          </div>
          <div v-if="connection.last_error" class="connection-error"><AlertTriangle :size="15" />{{ connection.last_error }}</div>
          <div class="connection-actions">
            <button v-if="connection.status !== 'demo'" class="button ghost small" @click="syncConnection(connection)"><RefreshCw :size="14" />Sincronizar</button>
            <button v-if="connection.status !== 'demo'" class="button ghost small" @click="configureWebhooks(connection)"><Webhook :size="14" />Webhooks</button>
            <button v-if="connection.status !== 'demo'" class="button ghost small" @click="toggleRemote(connection)"><Server :size="14" />Selecionar projetos<ChevronUp v-if="activeConnectionId === connection.id" :size="14" /><ChevronDown v-else :size="14" /></button>
            <button class="button ghost small danger-text" @click="removeConnection(connection)"><Trash2 :size="14" />Remover</button>
          </div>

          <div v-if="activeConnectionId === connection.id" class="remote-panel">
            <div v-if="remoteLoadingId === connection.id" class="remote-loading"><span class="spinner" />Consultando repositórios autorizados…</div>
            <template v-else>
              <header><div><strong>Repositórios disponíveis</strong><span>Marque os projetos que devem ser importados ou atualizados.</span></div><button class="button primary small" :disabled="!selectedRemote(connection.id).length" @click="importSelected(connection)"><Save :size="14" />Importar {{ selectedRemote(connection.id).length }}</button></header>
              <div class="remote-list">
                <label v-for="remote in remoteRepositories[connection.id] || []" :key="remote.github_id" class="remote-item"><input v-model="remote.selected" type="checkbox" /><Github :size="16" /><span><strong>{{ remote.full_name }}</strong><small>{{ remote.private ? 'Privado' : 'Público' }} · {{ remote.language || 'sem linguagem principal' }}</small></span><Check v-if="remote.selected" :size="16" /></label>
              </div>
            </template>
          </div>
        </article>
        <div v-if="!connections.length" class="empty-connections"><Github :size="27" /><strong>Nenhuma conta conectada</strong><span>Cadastre um token GitHub para iniciar.</span></div>
      </div>
    </section>

    <section class="settings-footer"><div><Server :size="17" /><span><strong>ARGWS Git Monitor</strong><small>API FastAPI · PostgreSQL · Redis · RabbitMQ · Celery · Vue PWA</small></span></div><span>Versão {{ appVersion }}</span></section>
  </div>
</template>

<style scoped>
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.settings-card,.github-section{padding:1.1rem;border:1px solid var(--border);border-radius:var(--radius-xl);background:linear-gradient(145deg,var(--surface),var(--surface-raised));box-shadow:var(--shadow-sm)}.settings-card>header,.connection-form>header{display:flex;align-items:center;gap:.7rem;padding-bottom:.85rem;border-bottom:1px solid var(--border-soft)}.card-icon{display:grid;place-items:center;width:2.5rem;height:2.5rem;color:var(--primary);border-radius:.8rem;background:color-mix(in srgb,var(--primary) 11%,var(--surface))}.settings-card header>div:last-child,.connection-form header>div{display:grid}.settings-card header span{color:var(--text-subtle);font-size:.62rem;font-weight:750;letter-spacing:.08em}.settings-card h3{margin:.1rem 0 0;color:var(--text-strong);font-size:.9rem}
.required-password{display:flex;align-items:flex-start;gap:.7rem;padding:.85rem;color:var(--warning);border:1px solid color-mix(in srgb,var(--warning) 30%,var(--border));border-radius:var(--radius-lg);background:color-mix(in srgb,var(--warning) 8%,var(--surface))}.required-password strong{font-size:.78rem}.required-password p{margin:.12rem 0 0;color:var(--text-muted);font-size:.68rem}
.account-summary{display:flex;align-items:center;gap:.8rem;padding:1rem 0}.large-avatar{display:grid;place-items:center;width:3.1rem;height:3.1rem;color:white;font-size:1.1rem;font-weight:800;border-radius:1rem;background:linear-gradient(145deg,var(--primary),var(--secondary))}.account-summary>div:last-child{display:grid}.account-summary strong{color:var(--text-strong);font-size:.8rem}.account-summary span{color:var(--text-muted);font-size:.7rem}.account-summary small{color:var(--primary-strong);font-size:.6rem}.password-form{display:grid;gap:.75rem}.setting-row{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.9rem 0;border-bottom:1px solid var(--border-soft)}.setting-row>div{display:grid}.setting-row strong,.theme-setting>strong{color:var(--text);font-size:.75rem}.setting-row span{color:var(--text-subtle);font-size:.65rem}.theme-setting{display:grid;gap:.65rem;padding:.9rem 0}.theme-options{display:grid;grid-template-columns:repeat(3,1fr);gap:.45rem}.theme-options button{display:flex;align-items:center;justify-content:center;gap:.4rem;padding:.65rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.7rem;background:var(--surface);font:inherit;font-size:.68rem;cursor:pointer}.theme-options button.active{color:var(--primary-strong);border-color:color-mix(in srgb,var(--primary) 35%,var(--border));background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.security-info{display:flex;align-items:flex-start;gap:.55rem;padding:.7rem;color:var(--success);border-radius:.7rem;background:color-mix(in srgb,var(--success) 7%,var(--surface))}.security-info p{margin:0;color:var(--text-muted);font-size:.65rem;line-height:1.45}
.github-section{display:grid;gap:1rem}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem}.section-heading>div{display:grid}.section-heading span:first-child{color:var(--primary-strong);font-size:.62rem;font-weight:780;letter-spacing:.08em}.section-heading h3{margin:.1rem 0;color:var(--text-strong);font-size:1rem}.section-heading p{margin:0;color:var(--text-muted);font-size:.7rem}
.connection-form{display:grid;gap:1rem;padding:1rem;border:1px solid color-mix(in srgb,var(--primary) 28%,var(--border));border-radius:var(--radius-lg);background:color-mix(in srgb,var(--primary) 4%,var(--surface))}.connection-form>header{color:var(--primary)}.connection-form header strong{color:var(--text-strong);font-size:.8rem}.connection-form header span{color:var(--text-muted);font-size:.67rem}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.full-field{grid-column:1/-1}.check-row{display:flex;align-items:flex-start;gap:.6rem;color:var(--text);cursor:pointer}.check-row input,.remote-item input{accent-color:var(--primary)}.check-row span{display:grid}.check-row strong{font-size:.72rem}.check-row small{color:var(--text-subtle);font-size:.62rem}.permission-box{display:flex;align-items:flex-start;gap:.6rem;padding:.75rem;color:var(--info);border-radius:.7rem;background:color-mix(in srgb,var(--info) 7%,var(--surface))}.permission-box strong{color:var(--text);font-size:.7rem}.permission-box p{margin:.15rem 0 0;color:var(--text-muted);font-size:.63rem;line-height:1.45}.connection-form footer{display:flex;justify-content:flex-end;gap:.55rem}
.connection-list{display:grid;gap:.75rem}.connection-skeleton{height:150px}.connection-card{overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-lg);background:var(--surface)}.connection-card.status-error{border-color:color-mix(in srgb,var(--danger) 30%,var(--border))}.connection-main{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem;padding:.9rem}.github-avatar{display:grid;place-items:center;width:2.6rem;height:2.6rem;color:var(--text);border-radius:.8rem;background:var(--surface-soft)}.connection-copy{display:grid;min-width:0}.connection-copy>div{display:flex;align-items:center;gap:.5rem}.connection-copy strong{color:var(--text-strong);font-size:.78rem}.connection-copy>span{color:var(--text-muted);font-size:.67rem}.connection-copy>small{color:var(--text-subtle);font-size:.6rem}.rate-info{display:grid;justify-items:end;color:var(--primary)}.rate-info span{color:var(--text-subtle);font-size:.56rem}.rate-info strong{color:var(--text);font-size:.78rem}.connection-error{display:flex;align-items:center;gap:.45rem;margin:0 .9rem .7rem;padding:.55rem;color:var(--danger);font-size:.63rem;border-radius:.55rem;background:color-mix(in srgb,var(--danger) 7%,var(--surface))}.connection-actions{display:flex;gap:.4rem;flex-wrap:wrap;padding:.65rem .9rem;border-top:1px solid var(--border-soft);background:var(--surface-raised)}.danger-text{color:var(--danger)!important;margin-left:auto}.remote-panel{padding:.9rem;border-top:1px solid var(--border);background:var(--surface-raised)}.remote-panel>header{display:flex;align-items:center;justify-content:space-between;gap:.8rem;margin-bottom:.65rem}.remote-panel header>div{display:grid}.remote-panel header strong{color:var(--text);font-size:.72rem}.remote-panel header span{color:var(--text-subtle);font-size:.62rem}.remote-loading{display:flex;align-items:center;gap:.5rem;color:var(--text-muted);font-size:.68rem}.remote-list{display:grid;grid-template-columns:repeat(2,1fr);gap:.4rem;max-height:360px;overflow:auto}.remote-item{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:.5rem;padding:.6rem;color:var(--text-muted);border:1px solid var(--border-soft);border-radius:.65rem;background:var(--surface);cursor:pointer}.remote-item>span{display:grid;min-width:0}.remote-item strong,.remote-item small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.remote-item strong{color:var(--text);font-size:.67rem}.remote-item small{color:var(--text-subtle);font-size:.58rem}.empty-connections{display:grid;justify-items:center;gap:.4rem;padding:2rem;color:var(--primary);border:1px dashed var(--border);border-radius:var(--radius-lg)}.empty-connections strong{color:var(--text);font-size:.76rem}.empty-connections span{color:var(--text-subtle);font-size:.66rem}
.settings-footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.8rem;color:var(--text-subtle);font-size:.62rem;border-top:1px solid var(--border)}.settings-footer>div{display:flex;align-items:center;gap:.55rem;color:var(--primary)}.settings-footer>div>span{display:grid}.settings-footer strong{color:var(--text);font-size:.66rem}.settings-footer small{color:var(--text-subtle);font-size:.58rem}
@media(max-width:950px){.settings-grid{grid-template-columns:1fr}.remote-list{grid-template-columns:1fr}}
@media(max-width:650px){.form-grid{grid-template-columns:1fr}.full-field{grid-column:auto}.connection-main{grid-template-columns:auto 1fr}.rate-info{grid-column:2;justify-items:start}.connection-actions .button{flex:1}.danger-text{margin-left:0}.remote-panel>header{display:grid}.remote-panel .button{width:100%}.setting-row{align-items:flex-start}.theme-options{grid-template-columns:1fr}.settings-footer{display:grid}.page-heading>.button{width:100%}}
</style>
