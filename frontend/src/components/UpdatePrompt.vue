<script setup lang="ts">
import { useRegisterSW } from 'virtual:pwa-register/vue'
import { RefreshCw, WifiOff, X } from 'lucide-vue-next'

const { offlineReady, needRefresh, updateServiceWorker } = useRegisterSW()
function close(): void {
  offlineReady.value = false
  needRefresh.value = false
}
</script>

<template>
  <div v-if="offlineReady || needRefresh" class="update-prompt">
    <WifiOff v-if="offlineReady" :size="19" />
    <RefreshCw v-else :size="19" />
    <div>
      <strong>{{ offlineReady ? 'Aplicação pronta para uso offline' : 'Nova versão disponível' }}</strong>
      <span>{{ offlineReady ? 'A interface básica continuará abrindo sem conexão.' : 'Atualize para carregar as melhorias.' }}</span>
    </div>
    <button v-if="needRefresh" class="button small primary" @click="updateServiceWorker(true)">Atualizar</button>
    <button class="icon-button" aria-label="Fechar" @click="close"><X :size="16" /></button>
  </div>
</template>

<style scoped>
.update-prompt { position:fixed; z-index:1500; left:50%; bottom:calc(5.4rem + env(safe-area-inset-bottom)); display:flex; align-items:center; gap:.75rem; width:min(580px,calc(100vw - 2rem)); padding:.85rem 1rem; color:var(--info); border:1px solid color-mix(in srgb,var(--info) 30%,var(--border)); border-radius:var(--radius-lg); background:color-mix(in srgb,var(--surface-raised) 95%,transparent); box-shadow:var(--shadow-lg); backdrop-filter:blur(18px); transform:translateX(-50%); }
.update-prompt > div { display:grid; flex:1; }
strong { color:var(--text-strong); font-size:.8rem; }
span { color:var(--text-muted); font-size:.7rem; }
@media (min-width: 900px) { .update-prompt { bottom:1.2rem; } }
</style>
