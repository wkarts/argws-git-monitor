<script setup lang="ts">
import { Home, SearchX } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import AppLogo from '../components/AppLogo.vue'
</script>

<template>
  <main class="not-found">
    <AppLogo />
    <div class="not-found-icon"><SearchX :size="34" /></div>
    <span>ERRO 404</span>
    <h1>Página não encontrada</h1>
    <p>O endereço informado não existe ou foi removido do ARGWS Git Monitor.</p>
    <RouterLink to="/" class="button primary"><Home :size="17" />Voltar ao dashboard</RouterLink>
  </main>
</template>

<style scoped>
.not-found{min-height:100dvh;display:grid;place-content:center;justify-items:center;gap:.75rem;padding:1.5rem;text-align:center;background:radial-gradient(circle at 50% 20%,color-mix(in srgb,var(--primary) 12%,transparent),transparent 35%),var(--background)}.not-found-icon{display:grid;place-items:center;width:4rem;height:4rem;margin-top:2rem;color:var(--primary);border-radius:1.2rem;background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.not-found>span{color:var(--primary-strong);font-size:.65rem;font-weight:800;letter-spacing:.15em}.not-found h1{margin:0;color:var(--text-strong);font-size:clamp(1.7rem,5vw,2.7rem)}.not-found p{max-width:440px;margin:0 0 .5rem;color:var(--text-muted);font-size:.8rem;line-height:1.55}
</style>
