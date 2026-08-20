<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  label: string
  value: string | number
  helper?: string
  icon: Component
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info'
}>()
</script>

<template>
  <article class="stat-card" :class="`tone-${tone || 'default'}`">
    <div class="stat-icon"><component :is="icon" :size="19" /></div>
    <div class="stat-copy">
      <span>{{ label }}</span>
      <strong>{{ value }}</strong>
      <small v-if="helper">{{ helper }}</small>
    </div>
  </article>
</template>

<style scoped>
.stat-card { display:flex; align-items:flex-start; gap:.85rem; min-height:112px; padding:1rem; border:1px solid var(--border); border-radius:var(--radius-lg); background:linear-gradient(145deg,var(--surface),var(--surface-raised)); box-shadow:var(--shadow-sm); }
.stat-icon { display:grid; place-items:center; width:2.35rem; height:2.35rem; border-radius:.8rem; color:var(--primary); background:color-mix(in srgb,var(--primary) 12%,var(--surface)); }
.stat-copy { display:grid; min-width:0; }
.stat-copy span { color:var(--text-muted); font-size:.76rem; font-weight:650; }
.stat-copy strong { margin-top:.2rem; color:var(--text-strong); font-size:1.65rem; line-height:1.1; }
.stat-copy small { margin-top:.28rem; color:var(--text-subtle); font-size:.7rem; }
.tone-success .stat-icon { color:var(--success); background:color-mix(in srgb,var(--success) 12%,var(--surface)); }
.tone-warning .stat-icon { color:var(--warning); background:color-mix(in srgb,var(--warning) 12%,var(--surface)); }
.tone-danger .stat-icon { color:var(--danger); background:color-mix(in srgb,var(--danger) 12%,var(--surface)); }
.tone-info .stat-icon { color:var(--info); background:color-mix(in srgb,var(--info) 12%,var(--surface)); }
</style>
