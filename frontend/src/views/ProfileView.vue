<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Camera, CheckCircle2, ImageOff, Save, ShieldCheck, UserRound } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { User } from '../types/api'

const auth = useAuthStore()
const dialogs = useDialogStore()
const toasts = useToastStore()
const saving = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const profile = reactive({
  name: '',
  job_title: '',
  bio: '',
  timezone: 'America/Bahia',
  locale: 'pt-BR'
})

const initials = computed(() =>
  (auth.user?.name || 'U')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
)

function fillFromUser(user: User | null): void {
  if (!user) return
  profile.name = user.name
  profile.job_title = user.job_title || ''
  profile.bio = user.bio || ''
  profile.timezone = user.timezone || 'America/Bahia'
  profile.locale = user.locale || 'pt-BR'
}
watch(() => auth.user, fillFromUser, { immediate: true })

async function saveProfile(): Promise<void> {
  saving.value = true
  try {
    const user = await api.patch<User>('/auth/profile', {
      name: profile.name.trim(),
      job_title: profile.job_title.trim() || null,
      bio: profile.bio.trim() || null,
      timezone: profile.timezone,
      locale: profile.locale,
      preferences: auth.user?.preferences || {}
    })
    auth.setUser(user)
    toasts.success('Perfil atualizado', 'As informações foram salvas.')
  } catch (error) {
    toasts.error('Não foi possível salvar', error instanceof ApiError ? error.message : undefined)
  } finally { saving.value = false }
}

async function uploadAvatar(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    toasts.warning('Formato inválido', 'Use JPEG, PNG ou WEBP.')
    input.value = ''
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    toasts.warning('Imagem muito grande', 'O avatar pode ter até 2 MB.')
    input.value = ''
    return
  }
  uploading.value = true
  try {
    const data = new FormData()
    data.append('avatar', file)
    const user = await api.post<User>('/auth/avatar', data)
    auth.setUser(user)
    toasts.success('Foto atualizada')
  } catch (error) {
    toasts.error('Falha ao enviar a foto', error instanceof ApiError ? error.message : undefined)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function removeAvatar(): Promise<void> {
  if (!auth.user?.avatar_url) return
  const accepted = await dialogs.askConfirmation({
    title: 'Remover foto de perfil?',
    message: 'A imagem atual será removida da sua conta do ARGWS Git Monitor. Você poderá enviar uma nova foto a qualquer momento.',
    tone: 'warning',
    confirmLabel: 'Remover foto',
  })
  if (!accepted) return
  try {
    const user = await api.delete<User>('/auth/avatar')
    auth.setUser(user)
    toasts.success('Foto removida')
  } catch (error) {
    toasts.error('Não foi possível remover', error instanceof ApiError ? error.message : undefined)
  }
}
</script>

<template>
  <div class="page-stack profile-page">
    <section class="page-heading">
      <div><span class="eyebrow">IDENTIDADE E PREFERÊNCIAS</span><h2>Meu perfil</h2><p>Foto, dados pessoais e preferências básicas da sua conta no ARGWS Git Monitor.</p></div>
    </section>

    <section class="profile-layout">
      <aside class="profile-card">
        <div class="avatar-large">
          <img v-if="auth.user?.avatar_url" :src="auth.user.avatar_url" :alt="auth.user.name" />
          <span v-else>{{ initials }}</span>
          <button class="avatar-action" :disabled="uploading" title="Alterar foto" @click="fileInput?.click()"><Camera :size="17" /></button>
          <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="uploadAvatar" />
        </div>
        <div class="profile-identity"><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span><small>{{ auth.user?.job_title || (auth.user?.is_superuser ? 'Administrador da plataforma' : 'Usuário') }}</small></div>
        <div class="profile-badges"><span :class="auth.user?.totp_enabled ? 'success' : 'warning'"><ShieldCheck :size="13" />2FA {{ auth.user?.totp_enabled ? 'ativo' : 'desligado' }}</span><span class="primary"><UserRound :size="13" />{{ auth.user?.is_superuser ? 'Administrador' : 'Usuário' }}</span></div>
        <div class="avatar-buttons"><button class="button secondary" :disabled="uploading" @click="fileInput?.click()"><Camera :size="15" />{{ uploading ? 'Enviando…' : 'Trocar foto' }}</button><button v-if="auth.user?.avatar_url" class="button ghost danger-text" @click="removeAvatar"><ImageOff :size="15" />Remover</button></div>
        <p>JPEG, PNG ou WEBP. Máximo 2 MB. A foto fica armazenada no banco e acompanha o backup da aplicação.</p>
      </aside>

      <section class="profile-form-card">
        <header><div><span class="eyebrow">DADOS DO PERFIL</span><h3>Informações da conta</h3></div><CheckCircle2 :size="19" /></header>
        <form @submit.prevent="saveProfile">
          <div class="profile-fields">
            <label class="field"><span>Nome de exibição</span><input v-model="profile.name" required maxlength="120" /></label>
            <label class="field"><span>Cargo / função</span><input v-model="profile.job_title" maxlength="160" placeholder="Ex.: Desenvolvimento e Infraestrutura" /></label>
            <label class="field"><span>Fuso horário</span><select v-model="profile.timezone"><option value="America/Bahia">America/Bahia</option><option value="America/Sao_Paulo">America/Sao_Paulo</option><option value="UTC">UTC</option></select></label>
            <label class="field"><span>Idioma</span><select v-model="profile.locale"><option value="pt-BR">Português (Brasil)</option><option value="en-US">English (US)</option></select></label>
            <label class="field bio-field"><span>Biografia / contexto</span><textarea v-model="profile.bio" maxlength="2000" placeholder="Informações úteis sobre sua função ou responsabilidade na plataforma." /></label>
          </div>
          <div class="profile-footer"><div><strong>{{ auth.user?.email }}</strong><span>O e-mail de login é administrado pelo painel de usuários.</span></div><button class="button primary" :disabled="saving"><Save :size="16" />{{ saving ? 'Salvando…' : 'Salvar perfil' }}</button></div>
        </form>
      </section>
    </section>
  </div>
</template>

<style scoped>
.profile-layout{display:grid;grid-template-columns:minmax(260px,.72fr) minmax(0,1.6fr);gap:1rem}.profile-card,.profile-form-card{border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.profile-card{display:grid;justify-items:center;align-content:start;gap:.85rem;padding:1.35rem;text-align:center}.avatar-large{position:relative;display:grid;place-items:center;width:8.5rem;height:8.5rem;border:4px solid var(--surface);border-radius:50%;color:white;background:linear-gradient(135deg,var(--primary),var(--secondary));box-shadow:0 0 0 1px var(--border),0 12px 35px color-mix(in srgb,var(--primary) 18%,transparent);font-size:2.2rem;font-weight:900;overflow:visible}.avatar-large img{width:100%;height:100%;object-fit:cover;border-radius:50%}.avatar-action{position:absolute;right:.15rem;bottom:.15rem;display:grid;place-items:center;width:2.35rem;height:2.35rem;color:white;border:3px solid var(--surface);border-radius:50%;background:var(--primary);cursor:pointer}.profile-identity{display:grid}.profile-identity strong{color:var(--text-strong);font-size:1.05rem}.profile-identity span{color:var(--text-muted);font-size:.72rem}.profile-identity small{margin-top:.15rem;color:var(--primary-strong);font-size:.64rem;font-weight:750}.profile-badges{display:flex;justify-content:center;flex-wrap:wrap;gap:.4rem}.profile-badges span{display:inline-flex;align-items:center;gap:.3rem;padding:.25rem .48rem;border:1px solid var(--border);border-radius:999px;color:var(--text-muted);background:var(--surface-soft);font-size:.59rem;font-weight:800}.profile-badges .success{color:var(--success)}.profile-badges .warning{color:var(--warning)}.profile-badges .primary{color:var(--primary-strong)}.avatar-buttons{display:flex;gap:.45rem}.profile-card>p{margin:0;color:var(--text-subtle);font-size:.62rem;line-height:1.5}.profile-form-card{overflow:hidden}.profile-form-card>header{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.1rem;border-bottom:1px solid var(--border-soft)}.profile-form-card h3{margin:.08rem 0;color:var(--text-strong)}.profile-form-card>header>svg{color:var(--success)}.profile-form-card form{display:grid}.profile-fields{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;padding:1.1rem}.bio-field{grid-column:1/-1}.bio-field textarea{min-height:150px}.profile-footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.1rem;border-top:1px solid var(--border-soft);background:var(--surface-soft)}.profile-footer>div{display:grid}.profile-footer strong{color:var(--text)}.profile-footer span{color:var(--text-muted);font-size:.62rem}.danger-text{color:var(--danger)!important}
@media(max-width:850px){.profile-layout{grid-template-columns:1fr}.profile-card{grid-template-columns:auto 1fr;justify-items:start;text-align:left}.avatar-large{grid-row:1/4;width:6rem;height:6rem}.profile-badges{justify-content:flex-start}.avatar-buttons,.profile-card>p{grid-column:1/-1}}@media(max-width:600px){.profile-card{display:grid;grid-template-columns:1fr;justify-items:center;text-align:center}.avatar-large{grid-row:auto}.profile-badges{justify-content:center}.profile-fields{grid-template-columns:1fr}.bio-field{grid-column:auto}.profile-footer{align-items:stretch;flex-direction:column}.profile-footer .button{width:100%}.avatar-buttons{width:100%;display:grid;grid-template-columns:1fr 1fr}.avatar-buttons .button{width:100%}}
</style>
