<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{ icon: Component; title: string; message: string }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon"><component :is="icon" :size="28" /></div>
    <h3>{{ title }}</h3>
    <p>{{ message }}</p>
    <slot />
  </div>
</template>

<style scoped>
.empty-state { display:grid; justify-items:center; gap:.65rem; padding:2.7rem 1.2rem; text-align:center; border:1px dashed var(--border); border-radius:var(--radius-xl); background:var(--surface); }
.empty-icon { display:grid; place-items:center; width:3.25rem; height:3.25rem; border-radius:1rem; color:var(--primary); background:color-mix(in srgb,var(--primary) 10%,var(--surface)); }
h3 { margin:.25rem 0 0; color:var(--text-strong); font-size:1rem; }
p { max-width:420px; margin:0; color:var(--text-muted); font-size:.82rem; line-height:1.5; }
</style>
