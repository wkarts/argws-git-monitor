<script setup lang="ts">
import { computed } from 'vue'
import { conclusionLabel, healthLabel } from '../services/format'
import type { HealthStatus } from '../types/api'

const props = defineProps<{
  value: string | null | undefined
  health?: boolean
  compact?: boolean
}>()

const normalized = computed(() => (props.value || 'unknown').toLowerCase())
const kind = computed(() => {
  if (['healthy', 'success', 'completed'].includes(normalized.value)) return 'success'
  if (['running', 'in_progress', 'queued', 'requested', 'waiting', 'pending'].includes(normalized.value)) return 'running'
  if (['failing', 'failure', 'cancelled', 'timed_out', 'action_required', 'startup_failure'].includes(normalized.value)) return 'error'
  if (['attention', 'neutral', 'stale'].includes(normalized.value)) return 'warning'
  return 'neutral'
})
const label = computed(() =>
  props.health ? healthLabel(normalized.value as HealthStatus) : conclusionLabel(normalized.value)
)
</script>

<template>
  <span class="status-badge" :class="[`is-${kind}`, { compact }]">
    <span class="status-dot" />
    {{ label }}
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
  width: fit-content;
  min-height: 1.72rem;
  padding: 0.26rem 0.62rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-muted);
  background: var(--surface-raised);
  font-size: 0.76rem;
  font-weight: 680;
  white-space: nowrap;
}
.status-badge.compact { min-height: 1.45rem; padding: 0.15rem 0.48rem; font-size: 0.7rem; }
.status-dot { width: 0.46rem; height: 0.46rem; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 14%, transparent); }
.is-success { color: var(--success); border-color: color-mix(in srgb, var(--success) 25%, var(--border)); background: color-mix(in srgb, var(--success) 8%, var(--surface)); }
.is-running { color: var(--info); border-color: color-mix(in srgb, var(--info) 28%, var(--border)); background: color-mix(in srgb, var(--info) 8%, var(--surface)); }
.is-running .status-dot { animation: pulse 1.6s infinite; }
.is-error { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 28%, var(--border)); background: color-mix(in srgb, var(--danger) 8%, var(--surface)); }
.is-warning { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 28%, var(--border)); background: color-mix(in srgb, var(--warning) 8%, var(--surface)); }
@keyframes pulse { 50% { opacity: .35; transform: scale(.75); } }
</style>
