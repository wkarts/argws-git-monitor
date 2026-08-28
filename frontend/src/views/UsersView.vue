<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  BriefcaseBusiness, Edit3, KeyRound, LockKeyhole, MonitorSmartphone, Plus, RefreshCw,
  Save, Search, ShieldCheck, ShieldOff, Trash2, UserCheck, Users, X
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { formatDateTime } from '../services/format'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { AdminOverview, AdminPasswordResetResponse, AdminUser, MessageResponse } from '../types/api'

type EnrichedAdminUser = AdminUser & {
  job_title?: string | null
  timezone?: string
  locale?: string
  avatar_updated_at?: string | null
  avatar_url?: string | null
}

const dialogs = useDialogStore()
const toasts = useToastStore()
const loading = ref(true)
const users = ref<EnrichedAdminUser[]>([])
const overview = ref<AdminOverview>({ total_users: 0, active_users: 0, administrators: 0, two_factor_enabled: 0, active_sessions: 0 })
const query = ref('')
const showCreate = ref(false)
const editingUser = ref<EnrichedAdminUser | null>(null)
const temporaryPassword = ref('')
const createForm = reactive({ name: '', email: '', job_title: '', password: '', is_superuser: false, is_active: true })
const editForm = reactive({ name: '', email: '', job_title: '', is_superuser: false, is_active: true, must_change_password: false })

const filteredUsers = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return users.value
  return users.value.filter((user) =>
    `${user.name} ${user.email} ${user.job_title || ''}`.toLowerCase().includes(term)
  )
})
const cards = computed(() => [
  { label: 'Usuários', value: overview.value.total_users, icon: Users },
  { label: 'Ativos', value: overview.value.active_users, icon: UserCheck },
  { label: 'Administradores', value: overview.value.administrators, icon: ShieldCheck },
  { label: 'Com 2FA', value: overview.value.two_factor_enabled, icon: LockKeyhole },
  { label: 'Sessões ativas', value: overview.value.active_sessions, icon: MonitorSmartphone }
])

function initials(user: EnrichedAdminUser): string {
  return user.name.split(/\s+/).filter(Boolean).slice(0,2).map((part) => part[0]?.toUpperCase()).join('') || 'U'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    ;[overview.value, users.value] = await Promise.all([
      api.get<AdminOverview>('/admin/overview'),
      api.get<EnrichedAdminUser[]>('/admin/users')
    ])
  } catch (error) {
    toasts.error('Falha no painel de usuários', error instanceof ApiError ? error.message : undefined)
  } finally { loading.value = false }
}

async function createUser(): Promise<void> {
  if (createForm.password.length < 12) { toasts.warning('Senha muito curta', 'Use pelo menos 12 caracteres.'); return }
  try {
    await api.post<EnrichedAdminUser>('/admin/users', {
      name: createForm.name,
      email: createForm.email,
      job_title: createForm.job_title.trim() || null,
      password: createForm.password,
      is_superuser: createForm.is_superuser,
      is_active: createForm.is_active,
      must_change_password: true
    })
    Object.assign(createForm, { name: '', email: '', job_title: '', password: '', is_superuser: false, is_active: true })
    showCreate.value = false
    toasts.success('Usuário criado', 'A conta exigirá troca da senha no primeiro acesso.')
    await load()
  } catch (error) { toasts.error('Não foi possível criar', error instanceof ApiError ? error.message : undefined) }
}

function openEdit(user: EnrichedAdminUser): void {
  editingUser.value = user
  Object.assign(editForm, {
    name: user.name,
    email: user.email,
    job_title: user.job_title || '',
    is_superuser: user.is_superuser,
    is_active: user.is_active,
    must_change_password: user.must_change_password
  })
}
function closeEdit(): void { editingUser.value = null }

async function saveEdit(): Promise<void> {
  if (!editingUser.value) return
  try {
    await api.patch<EnrichedAdminUser>(`/admin/users/${editingUser.value.id}`, {
      name: editForm.name.trim(),
      email: editForm.email.trim(),
      job_title: editForm.job_title.trim() || null,
      is_superuser: editForm.is_superuser,
      is_active: editForm.is_active,
      must_change_password: editForm.must_change_password
    })
    toasts.success('Usuário atualizado')
    closeEdit()
    await load()
  } catch (error) { toasts.error('Alteração recusada', error instanceof ApiError ? error.message : undefined) }
}

async function toggle(user: EnrichedAdminUser, field: 'is_active' | 'is_superuser'): Promise<void> {
  const action = field === 'is_active'
    ? (user.is_active ? 'desativar esta conta' : 'ativar esta conta')
    : (user.is_superuser ? 'remover privilégios administrativos' : 'conceder privilégios administrativos')
  const accepted = await dialogs.askConfirmation({
    title: field === 'is_active' ? 'Alterar estado da conta?' : 'Alterar privilégios administrativos?',
    message: `${user.name}: ${action}.`,
    tone: user[field] ? 'warning' : 'info',
    confirmLabel: 'Confirmar alteração',
  })
  if (!accepted) return
  try {
    await api.patch<EnrichedAdminUser>(`/admin/users/${user.id}`, { [field]: !user[field] })
    await load()
  } catch (error) { toasts.error('Alteração recusada', error instanceof ApiError ? error.message : undefined) }
}

async function resetPassword(user: EnrichedAdminUser): Promise<void> {
  const accepted = await dialogs.askConfirmation({
    title: 'Gerar nova senha temporária?',
    message: `${user.name} terá a credencial redefinida e todas as sessões existentes serão revogadas. A nova senha será exibida uma única vez.`,
    tone: 'warning',
    confirmLabel: 'Gerar nova senha',
  })
  if (!accepted) return
  try {
    const response = await api.post<AdminPasswordResetResponse>(`/admin/users/${user.id}/reset-password`)
    temporaryPassword.value = response.temporary_password
    toasts.success('Senha temporária criada', 'Copie-a agora; ela não ficará exposta novamente.')
    await load()
  } catch (error) { toasts.error('Falha ao redefinir senha', error instanceof ApiError ? error.message : undefined) }
}

async function revokeSessions(user: EnrichedAdminUser): Promise<void> {
  const accepted = await dialogs.askConfirmation({
    title: 'Revogar todas as sessões?',
    message: `${user.name} será desconectado de todos os dispositivos e precisará autenticar novamente.`,
    tone: 'warning',
    confirmLabel: 'Revogar sessões',
  })
  if (!accepted) return
  try {
    const response = await api.post<MessageResponse>(`/admin/users/${user.id}/revoke-sessions`)
    toasts.success('Sessões revogadas', response.message)
    await load()
  } catch (error) { toasts.error('Falha ao revogar sessões', error instanceof ApiError ? error.message : undefined) }
}

async function reset2fa(user: EnrichedAdminUser): Promise<void> {
  const accepted = await dialogs.askConfirmation({
    title: 'Redefinir 2FA?',
    message: `O segundo fator de ${user.name} será removido. O usuário precisará configurar um novo autenticador antes de voltar a operar normalmente.`,
    tone: 'danger',
    confirmLabel: 'Redefinir 2FA',
  })
  if (!accepted) return
  try {
    const response = await api.post<MessageResponse>(`/admin/users/${user.id}/reset-2fa`)
    toasts.success('2FA redefinido', response.message)
    await load()
  } catch (error) { toasts.error('Falha ao redefinir 2FA', error instanceof ApiError ? error.message : undefined) }
}

async function removeUser(user: EnrichedAdminUser): Promise<void> {
  const typed = await dialogs.askText({
    title: 'Excluir usuário definitivamente?',
    message: `${user.name} será removido do ARGWS Git Monitor. Digite o e-mail da conta para confirmar a exclusão.`,
    tone: 'danger',
    confirmLabel: 'Excluir usuário',
    promptLabel: 'Confirmação obrigatória',
    promptExpected: user.email,
    promptPlaceholder: user.email,
  })
  if (typed !== user.email) return
  try {
    const response = await api.delete<MessageResponse>(`/admin/users/${user.id}`)
    toasts.success('Usuário removido', response.message)
    await load()
  } catch (error) { toasts.error('Falha ao remover', error instanceof ApiError ? error.message : undefined) }
}

onMounted(load)
</script>

<template>
  <div class="page-stack users-page">
    <section class="page-heading">
      <div><span class="eyebrow">ADMINISTRAÇÃO DA PLATAFORMA</span><h2>Usuários e segurança</h2><p>Perfis, fotos, papéis, 2FA, sessões, credenciais e acesso administrativo em um painel responsivo.</p></div>
      <div class="button-row"><button class="button secondary" @click="load"><RefreshCw :size="16" />Atualizar</button><button class="button primary" @click="showCreate = true"><Plus :size="16" />Novo usuário</button></div>
    </section>

    <section class="admin-metrics"><article v-for="card in cards" :key="card.label"><div><component :is="card.icon" :size="19" /></div><span><strong>{{ card.value }}</strong><small>{{ card.label }}</small></span></article></section>

    <section v-if="showCreate" class="create-user panel">
      <header><div><span class="eyebrow">NOVA CONTA</span><h3>Criar usuário</h3></div><button class="icon-button" @click="showCreate = false"><X :size="17" /></button></header>
      <form @submit.prevent="createUser">
        <label class="field"><span>Nome</span><input v-model="createForm.name" required maxlength="120" /></label>
        <label class="field"><span>E-mail</span><input v-model="createForm.email" type="email" required /></label>
        <label class="field"><span>Cargo / função</span><input v-model="createForm.job_title" maxlength="160" placeholder="Ex.: DevOps" /></label>
        <label class="field"><span>Senha temporária</span><input v-model="createForm.password" type="password" minlength="12" required /></label>
        <label class="toggle-line"><input v-model="createForm.is_superuser" type="checkbox" /><span>Administrador</span></label>
        <button class="button primary">Criar conta</button>
      </form>
    </section>

    <section v-if="editingUser" class="edit-user panel">
      <header><div class="edit-identity"><div class="avatar medium"><img v-if="editingUser.avatar_url" :src="editingUser.avatar_url" :alt="editingUser.name" /><span v-else>{{ initials(editingUser) }}</span></div><div><span class="eyebrow">EDITAR CONTA</span><h3>{{ editingUser.name }}</h3><small>{{ editingUser.email }}</small></div></div><button class="icon-button" @click="closeEdit"><X :size="17" /></button></header>
      <form @submit.prevent="saveEdit">
        <label class="field"><span>Nome</span><input v-model="editForm.name" required maxlength="120" /></label>
        <label class="field"><span>E-mail de login</span><input v-model="editForm.email" type="email" required /></label>
        <label class="field"><span>Cargo / função</span><input v-model="editForm.job_title" maxlength="160" /></label>
        <label class="toggle-line"><input v-model="editForm.is_active" type="checkbox" /><span>Conta ativa</span></label>
        <label class="toggle-line"><input v-model="editForm.is_superuser" type="checkbox" /><span>Administrador</span></label>
        <label class="toggle-line"><input v-model="editForm.must_change_password" type="checkbox" /><span>Exigir troca de senha</span></label>
        <button class="button primary"><Save :size="15" />Salvar alterações</button>
      </form>
    </section>

    <section v-if="temporaryPassword" class="temporary-password"><KeyRound :size="20" /><div><strong>Senha temporária gerada</strong><code>{{ temporaryPassword }}</code><small>Copie e envie por canal seguro. Ela não será mostrada novamente.</small></div><button class="button ghost compact" @click="temporaryPassword = ''">Ocultar</button></section>

    <section class="users-toolbar"><label class="search-field"><Search :size="17" /><input v-model="query" type="search" placeholder="Buscar nome, e-mail ou função…" /></label><span>{{ filteredUsers.length }} de {{ users.length }} conta(s)</span></section>

    <section class="user-list">
      <div v-if="loading" class="user-loading"><span v-for="n in 5" :key="n" class="skeleton" /></div>
      <article v-for="user in filteredUsers" v-else :key="user.id" class="user-card">
        <div class="identity"><div class="avatar"><img v-if="user.avatar_url" :src="user.avatar_url" :alt="user.name" /><span v-else>{{ initials(user) }}</span></div><div><strong>{{ user.name }}</strong><span>{{ user.email }}</span><small><BriefcaseBusiness :size="12" />{{ user.job_title || 'Função não informada' }}</small><small>Último acesso: {{ formatDateTime(user.last_login_at) }}</small></div></div>
        <div class="security-column"><div class="badges"><span :class="['badge', user.is_active ? 'success' : 'muted']">{{ user.is_active ? 'Ativo' : 'Inativo' }}</span><span v-if="user.is_superuser" class="badge primary">Administrador</span><span :class="['badge', user.totp_enabled ? 'success' : 'warning']">2FA {{ user.totp_enabled ? 'ativo' : 'desligado' }}</span><span v-if="user.must_change_password" class="badge warning">Troca de senha pendente</span></div><small>{{ user.timezone || 'America/Bahia' }} · {{ user.locale || 'pt-BR' }}</small></div>
        <div class="stats"><span><strong>{{ user.repository_count }}</strong><small>repositórios</small></span><span><strong>{{ user.github_connection_count }}</strong><small>conexões</small></span><span><strong>{{ user.active_session_count }}</strong><small>sessões</small></span></div>
        <div class="actions"><button class="button secondary compact" @click="openEdit(user)"><Edit3 :size="14" />Editar perfil</button><button class="button ghost compact" @click="toggle(user,'is_active')"><UserCheck :size="14" />{{ user.is_active ? 'Desativar' : 'Ativar' }}</button><button class="button ghost compact" @click="toggle(user,'is_superuser')"><ShieldCheck :size="14" />{{ user.is_superuser ? 'Remover admin' : 'Tornar admin' }}</button><button class="button ghost compact" @click="resetPassword(user)"><KeyRound :size="14" />Nova senha</button><button class="button ghost compact" @click="revokeSessions(user)"><MonitorSmartphone :size="14" />Revogar sessões</button><button v-if="user.totp_enabled" class="button ghost compact" @click="reset2fa(user)"><ShieldOff :size="14" />Resetar 2FA</button><button class="button ghost compact danger-text" @click="removeUser(user)"><Trash2 :size="14" />Excluir</button></div>
      </article>
    </section>
  </div>
</template>

<style scoped>
.admin-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.7rem}.admin-metrics article{display:flex;align-items:center;gap:.65rem;padding:.9rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface);box-shadow:var(--shadow-sm)}.admin-metrics article>div{display:grid;place-items:center;width:2.35rem;height:2.35rem;border-radius:.7rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.admin-metrics span{display:grid}.admin-metrics strong{color:var(--text-strong);font-size:1.15rem}.admin-metrics small{color:var(--text-muted);font-size:.64rem;font-weight:700}.panel{padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.create-user header,.edit-user header{display:flex;align-items:center;justify-content:space-between}.create-user h3,.edit-user h3{margin:.1rem 0;color:var(--text-strong)}.create-user form,.edit-user form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));align-items:end;gap:.7rem;margin-top:1rem}.toggle-line{display:flex;align-items:center;gap:.45rem;min-height:2.65rem;color:var(--text);font-size:.72rem}.edit-identity{display:flex;align-items:center;gap:.7rem}.edit-identity>div:last-child{display:grid}.edit-identity small{color:var(--text-muted)}.temporary-password{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.8rem;padding:.85rem 1rem;border:1px solid color-mix(in srgb,var(--warning) 35%,var(--border));border-radius:.85rem;background:color-mix(in srgb,var(--warning) 7%,var(--surface));color:var(--warning)}.temporary-password>div{display:grid;gap:.25rem}.temporary-password strong{color:var(--text-strong)}.temporary-password code{width:max-content;max-width:100%;padding:.35rem .5rem;color:var(--text-strong);border-radius:.45rem;background:var(--surface-soft);font-weight:800;word-break:break-all}.temporary-password small{color:var(--text-muted)}.users-toolbar{display:flex;align-items:center;justify-content:space-between;gap:1rem}.users-toolbar .search-field{flex:1}.users-toolbar>span{color:var(--text-muted);font-size:.7rem}.user-list{display:grid;gap:.65rem}.user-card{display:grid;grid-template-columns:minmax(260px,1.25fr) minmax(240px,1fr) minmax(220px,.75fr);align-items:center;gap:.85rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.identity{display:flex;align-items:center;gap:.75rem;min-width:0}.avatar{display:grid;place-items:center;width:3.2rem;height:3.2rem;overflow:hidden;flex:0 0 auto;border-radius:50%;color:white;background:linear-gradient(135deg,var(--primary),var(--secondary));font-weight:850}.avatar.medium{width:3rem;height:3rem}.avatar img{width:100%;height:100%;object-fit:cover}.identity>div:last-child{display:grid;min-width:0}.identity strong{color:var(--text-strong)}.identity span,.identity small{display:flex;align-items:center;gap:.25rem;overflow:hidden;color:var(--text-muted);font-size:.64rem;text-overflow:ellipsis;white-space:nowrap}.security-column{display:grid;gap:.35rem}.security-column>small{color:var(--text-subtle);font-size:.58rem}.badges,.actions{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem}.badge{padding:.22rem .45rem;border-radius:999px;font-size:.57rem;font-weight:800;border:1px solid var(--border);color:var(--text-muted);background:var(--surface-soft)}.badge.success{color:var(--success);border-color:color-mix(in srgb,var(--success) 28%,var(--border))}.badge.warning{color:var(--warning)}.badge.primary{color:var(--primary-strong)}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:.35rem}.stats span{display:grid;padding:.5rem;border:1px solid var(--border-soft);border-radius:.65rem;background:var(--surface-soft)}.stats strong{color:var(--text-strong);font-size:.92rem}.stats small{color:var(--text-muted);font-size:.53rem}.actions{grid-column:1/-1;padding-top:.65rem;border-top:1px solid var(--border-soft)}.user-loading{display:grid;gap:.65rem}.user-loading span{height:120px;border-radius:1rem}.danger-text{color:var(--danger)!important}
@media(max-width:1100px){.admin-metrics{grid-template-columns:repeat(3,1fr)}.user-card{grid-template-columns:1fr 1fr}.stats{grid-column:1/-1}.create-user form,.edit-user form{grid-template-columns:1fr 1fr}}@media(max-width:680px){.admin-metrics{grid-template-columns:1fr 1fr}.create-user form,.edit-user form{grid-template-columns:1fr}.user-card{grid-template-columns:1fr}.badges,.stats,.actions{grid-column:auto}.actions{display:grid;grid-template-columns:1fr 1fr}.actions .button{width:100%}.temporary-password{grid-template-columns:auto 1fr}.temporary-password>.button{grid-column:1/-1}.users-toolbar{align-items:stretch;flex-direction:column}}
</style>