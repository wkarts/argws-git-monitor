<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    value: string | number
    label: string
    helper: string
    icon: Component
    tone?: 'primary' | 'success' | 'warning' | 'danger'
  }>(),
  { tone: 'primary' }
)
</script>

<template>
  <article class="overview-metric" :class="`tone-${tone}`">
    <div class="overview-metric-icon"><component :is="icon" :size="24" :stroke-width="2.2" /></div>
    <div class="overview-metric-copy">
      <div><strong>{{ value }}</strong><span>{{ label }}</span></div>
      <small>{{ helper }}</small>
    </div>
  </article>
</template>

<style scoped>
.overview-metric {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.9rem;
  min-width: 0;
  min-height: 104px;
  padding: 1rem;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 0.9rem;
  background:
    radial-gradient(circle at 12% 20%, color-mix(in srgb, var(--metric-color) 11%, transparent), transparent 42%),
    linear-gradient(145deg, var(--surface), var(--surface-raised));
  box-shadow: var(--shadow-sm);
}
.overview-metric::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--metric-color) 68%, transparent), transparent);
  opacity: 0.65;
}
.overview-metric-icon {
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  width: 3.2rem;
  height: 3.2rem;
  color: var(--metric-color);
  border: 1px solid color-mix(in srgb, var(--metric-color) 28%, var(--border));
  border-radius: 50%;
  background: color-mix(in srgb, var(--metric-color) 13%, var(--surface));
  box-shadow: 0 0 0 7px color-mix(in srgb, var(--metric-color) 5%, transparent);
}
.overview-metric-copy {
  display: grid;
  min-width: 0;
}
.overview-metric-copy > div {
  display: flex;
  align-items: baseline;
  gap: 0.48rem;
  min-width: 0;
}
.overview-metric strong {
  color: var(--text-strong);
  font-size: clamp(1.4rem, 2vw, 1.8rem);
  line-height: 1;
}
.overview-metric span {
  overflow: hidden;
  color: var(--text);
  font-size: 0.78rem;
  font-weight: 720;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.overview-metric small {
  margin-top: 0.25rem;
  color: var(--text-subtle);
  font-size: 0.65rem;
}
.tone-primary { --metric-color: var(--primary); }
.tone-success { --metric-color: var(--success); }
.tone-warning { --metric-color: var(--warning); }
.tone-danger { --metric-color: var(--danger); }

@media (max-width: 480px) {
  .overview-metric { min-height: 90px; padding: 0.85rem; }
  .overview-metric-icon { width: 2.8rem; height: 2.8rem; }
}
</style>
