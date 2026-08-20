<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ score: number; size?: number }>(), { size: 72 })
const safeScore = computed(() => Math.max(0, Math.min(100, props.score)))
const tone = computed(() => {
  if (safeScore.value >= 85) return 'var(--success)'
  if (safeScore.value >= 65) return 'var(--warning)'
  return 'var(--danger)'
})
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  background: `conic-gradient(${tone.value} ${safeScore.value * 3.6}deg, var(--surface-soft) 0deg)`
}))
</script>

<template>
  <div class="health-ring" :style="style" role="img" :aria-label="`Saúde ${safeScore}%`">
    <div class="health-ring-center">
      <strong>{{ safeScore }}</strong>
      <span>%</span>
    </div>
  </div>
</template>

<style scoped>
.health-ring { display: grid; place-items: center; border-radius: 50%; flex: 0 0 auto; }
.health-ring-center { width: 76%; height: 76%; display: grid; place-content: center; text-align: center; border-radius: 50%; background: var(--surface); box-shadow: inset 0 0 0 1px var(--border); line-height: .9; }
.health-ring-center strong { color: var(--text-strong); font-size: 1.02rem; }
.health-ring-center span { color: var(--text-muted); font-size: .62rem; margin-top: .2rem; }
</style>
