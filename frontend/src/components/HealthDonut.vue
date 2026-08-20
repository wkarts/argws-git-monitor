<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    score: number
    healthy: number
    running: number
    critical: number
    unknown: number
    size?: number
  }>(),
  { size: 170 }
)

const normalizedScore = computed(() => Math.max(0, Math.min(100, Math.round(props.score))))
const total = computed(() => Math.max(props.healthy + props.running + props.critical + props.unknown, 1))
const healthyEnd = computed(() => (props.healthy / total.value) * 360)
const runningEnd = computed(() => healthyEnd.value + (props.running / total.value) * 360)
const criticalEnd = computed(() => runningEnd.value + (props.critical / total.value) * 360)
const ringStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  background: `conic-gradient(
    var(--success) 0deg ${healthyEnd.value}deg,
    var(--warning) ${healthyEnd.value}deg ${runningEnd.value}deg,
    var(--danger) ${runningEnd.value}deg ${criticalEnd.value}deg,
    var(--text-subtle) ${criticalEnd.value}deg 360deg
  )`
}))
</script>

<template>
  <div class="health-donut" :style="ringStyle" role="img" :aria-label="`Saúde geral ${normalizedScore}%`">
    <div class="health-donut-center">
      <strong>{{ normalizedScore }}%</strong>
      <span>saúde geral</span>
    </div>
  </div>
</template>

<style scoped>
.health-donut {
  position: relative;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  max-width: 100%;
  border-radius: 50%;
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--border) 82%, transparent),
    0 0 38px color-mix(in srgb, var(--success) 9%, transparent);
}
.health-donut::before {
  content: '';
  position: absolute;
  inset: 10%;
  border-radius: inherit;
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--border);
}
.health-donut-center {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  line-height: 1;
}
.health-donut-center strong {
  color: var(--text-strong);
  font-size: clamp(1.45rem, 3vw, 2rem);
  letter-spacing: -0.04em;
}
.health-donut-center span {
  margin-top: 0.45rem;
  color: var(--text-muted);
  font-size: 0.66rem;
}
</style>
