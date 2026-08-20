<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-vue-next'
import { useToastStore } from '../stores/toast'

const toasts = useToastStore()
const icons = { success: CheckCircle2, error: XCircle, warning: AlertTriangle, info: Info }
</script>

<template>
  <Teleport to="body">
    <TransitionGroup name="toast" tag="div" class="toast-host" aria-live="polite">
      <article v-for="item in toasts.items" :key="item.id" class="toast-item" :class="`is-${item.kind}`">
        <component :is="icons[item.kind]" :size="20" class="toast-icon" />
        <div>
          <strong>{{ item.title }}</strong>
          <p v-if="item.message">{{ item.message }}</p>
        </div>
        <button type="button" aria-label="Fechar" @click="toasts.remove(item.id)"><X :size="16" /></button>
      </article>
    </TransitionGroup>
  </Teleport>
</template>

<style scoped>
.toast-host { position:fixed; z-index:2000; top:max(1rem,env(safe-area-inset-top)); right:1rem; display:grid; gap:.65rem; width:min(390px,calc(100vw - 2rem)); pointer-events:none; }
.toast-item { display:grid; grid-template-columns:auto 1fr auto; gap:.75rem; align-items:start; padding:.9rem; border:1px solid var(--border); border-radius:var(--radius-lg); background:color-mix(in srgb,var(--surface-raised) 94%,transparent); box-shadow:var(--shadow-lg); backdrop-filter:blur(18px); pointer-events:auto; }
.toast-icon { color:var(--info); margin-top:.08rem; }
.toast-item.is-success .toast-icon { color:var(--success); }
.toast-item.is-warning .toast-icon { color:var(--warning); }
.toast-item.is-error .toast-icon { color:var(--danger); }
strong { display:block; color:var(--text-strong); font-size:.82rem; }
p { margin:.22rem 0 0; color:var(--text-muted); font-size:.76rem; line-height:1.35; }
button { padding:.1rem; color:var(--text-subtle); background:none; border:0; cursor:pointer; }
.toast-enter-active,.toast-leave-active { transition:all .22s ease; }
.toast-enter-from,.toast-leave-to { opacity:0; transform:translateX(18px); }
</style>
