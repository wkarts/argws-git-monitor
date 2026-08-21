<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Eye, EyeOff, Github, KeyRound, LockKeyhole, Mail, ShieldCheck } from 'lucide-vue-next'
import AppLogo from '../components/AppLogo.vue'
import { ApiError } from '../services/api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const appVersion = String(import.meta.env.VITE_APP_VERSION || '0.3.0')
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const otpCode = ref('')
const requiresTwoFactor = ref(false)
const showPassword = ref(false)
const errorMessage = ref('')
const canSubmit = computed(() => {
  if (auth.busy || email.value.trim().length <= 3 || !password.value.length) return false
  if (requiresTwoFactor.value && otpCode.value.trim().length < 6) return false
  return true
})

async function submit(): Promise<void> {
  errorMessage.value = ''
  try {
    const user = await auth.login(
      email.value.trim(),
      password.value,
      requiresTwoFactor.value ? otpCode.value : undefined
    )
    if (user.must_change_password) {
      await router.replace({ name: 'settings', query: { password: 'required' } })
      return
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (error) {
    if (error instanceof ApiError && error.message === '2FA_REQUIRED') {
      requiresTwoFactor.value = true
      otpCode.value = ''
      errorMessage.value = 'Informe o código do autenticador ou um código de recuperação.'
      return
    }
    errorMessage.value = error instanceof ApiError ? error.message : 'Não foi possível entrar.'
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-showcase">
      <div class="showcase-content">
        <AppLogo />
        <div class="showcase-copy">
          <span class="eyebrow">CENTRAL DE DESENVOLVIMENTO</span>
          <h1>Seus projetos sob controle, em qualquer tela.</h1>
          <p>Repositórios privados e públicos, Actions, pull requests, releases, filas e alertas reunidos em uma PWA rápida e segura.</p>
        </div>
        <div class="feature-list">
          <div><Github :size="19" /><span><strong>GitHub operacional</strong><small>Sincronização, webhooks e gestão de repositórios</small></span></div>
          <div><ShieldCheck :size="19" /><span><strong>2FA e sessões</strong><small>TOTP, códigos de recuperação e revogação</small></span></div>
          <div><LockKeyhole :size="19" /><span><strong>Credenciais protegidas</strong><small>Tokens criptografados somente no servidor</small></span></div>
        </div>
      </div>
    </section>

    <section class="login-panel">
      <form class="login-card" @submit.prevent="submit">
        <div class="mobile-brand"><AppLogo /></div>
        <div class="form-heading">
          <span>ACESSO SEGURO</span>
          <h2>{{ requiresTwoFactor ? 'Confirme sua identidade' : 'Bem-vindo ao Git Monitor' }}</h2>
          <p v-if="requiresTwoFactor">Sua conta possui autenticação em duas etapas.</p>
        </div>

        <div v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</div>

        <label class="field">
          <span>E-mail</span>
          <div class="input-with-icon">
            <Mail :size="17" />
            <input v-model="email" type="email" autocomplete="username" placeholder="seu@email.com" required :readonly="requiresTwoFactor" />
          </div>
        </label>

        <label class="field">
          <span>Senha</span>
          <div class="input-with-icon">
            <LockKeyhole :size="17" />
            <input v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="Sua senha" required :readonly="requiresTwoFactor" />
            <button type="button" class="input-action" :aria-label="showPassword ? 'Ocultar senha' : 'Mostrar senha'" @click="showPassword = !showPassword">
              <EyeOff v-if="showPassword" :size="17" />
              <Eye v-else :size="17" />
            </button>
          </div>
        </label>

        <label v-if="requiresTwoFactor" class="field otp-field">
          <span>Código do autenticador ou recuperação</span>
          <div class="input-with-icon">
            <KeyRound :size="17" />
            <input v-model="otpCode" type="text" inputmode="numeric" autocomplete="one-time-code" placeholder="000000" autofocus required />
          </div>
        </label>

        <button class="button primary large full" type="submit" :disabled="!canSubmit">
          <span v-if="auth.busy" class="spinner" />
          {{ auth.busy ? 'Autenticando…' : requiresTwoFactor ? 'Validar 2FA' : 'Entrar no monitor' }}
        </button>

        <button v-if="requiresTwoFactor" type="button" class="button ghost full" @click="requiresTwoFactor = false; otpCode = ''; errorMessage = ''">
          Voltar e trocar a conta
        </button>

        <p class="security-note"><ShieldCheck :size="15" /> Acesso protegido por sessão revogável e autenticação em duas etapas opcional.</p>
      </form>
      <footer>ARGWS Git Monitor · versão {{ appVersion }}</footer>
    </section>
  </main>
</template>

<style scoped>
.login-page { min-height:100dvh; display:grid; grid-template-columns:minmax(420px,1.1fr) minmax(440px,.9fr); background:var(--background); }
.login-showcase { position:relative; display:grid; place-items:center; overflow:hidden; padding:clamp(2rem,6vw,6rem); background:radial-gradient(circle at 18% 18%,rgba(56,189,248,.22),transparent 32%),radial-gradient(circle at 80% 80%,rgba(168,85,247,.2),transparent 34%),linear-gradient(145deg,#080d19,#111a31); }
.login-showcase::before { content:""; position:absolute; inset:0; opacity:.16; background-image:linear-gradient(rgba(255,255,255,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.12) 1px,transparent 1px); background-size:38px 38px; mask-image:linear-gradient(to bottom,black,transparent 95%); }
.showcase-content { position:relative; z-index:1; display:grid; gap:clamp(2.5rem,7vh,5rem); width:min(680px,100%); }
.showcase-copy { display:grid; gap:1rem; }
.eyebrow { color:#7dd3fc; font-size:.7rem; font-weight:800; letter-spacing:.18em; }
h1 { max-width:650px; margin:0; color:white; font-size:clamp(2.35rem,5vw,4.8rem); line-height:1.02; letter-spacing:-.045em; }
.showcase-copy p { max-width:590px; margin:0; color:#c2cee0; font-size:clamp(.95rem,1.4vw,1.15rem); line-height:1.65; }
.feature-list { display:grid; grid-template-columns:repeat(3,1fr); gap:.85rem; }
.feature-list > div { display:flex; gap:.65rem; padding:.9rem; color:#7dd3fc; border:1px solid rgba(255,255,255,.13); border-radius:1rem; background:rgba(255,255,255,.055); backdrop-filter:blur(12px); }
.feature-list span { display:grid; gap:.2rem; }
.feature-list strong { color:#f5f8ff; font-size:.72rem; }
.feature-list small { color:#aab9cf; font-size:.62rem; line-height:1.35; }
.login-panel { display:grid; place-items:center; align-content:center; gap:1.5rem; padding:clamp(1.2rem,5vw,5rem); background:var(--background); }
.login-card { display:grid; gap:1.15rem; width:min(440px,100%); padding:clamp(1.35rem,4vw,2.3rem); border:1px solid var(--border); border-radius:1.4rem; background:var(--surface); box-shadow:var(--shadow-lg); }
.mobile-brand { display:none; }
.form-heading { display:grid; gap:.42rem; margin-bottom:.35rem; }
.form-heading > span { color:var(--primary-strong); font-size:.68rem; font-weight:800; letter-spacing:.12em; }
.form-heading p { margin:0; color:var(--text-muted); font-size:.78rem; }
h2 { margin:0; color:var(--text-strong); font-size:1.55rem; letter-spacing:-.02em; }
.form-error { padding:.72rem .8rem; color:var(--danger); font-size:.76rem; font-weight:650; border:1px solid color-mix(in srgb,var(--danger) 32%,var(--border)); border-radius:.72rem; background:color-mix(in srgb,var(--danger) 8%,var(--surface)); }
.otp-field input { font-size:1.2rem; font-weight:800; letter-spacing:.16em; }
.security-note { display:flex; align-items:center; justify-content:center; gap:.4rem; margin:.1rem 0 0; color:var(--text-muted); font-size:.68rem; text-align:center; }
footer { color:var(--text-muted); font-size:.65rem; }
@media (max-width: 980px) { .login-page { grid-template-columns:1fr; } .login-showcase { display:none; } .login-panel { min-height:100dvh; } .mobile-brand { display:block; margin-bottom:.5rem; } }
</style>
