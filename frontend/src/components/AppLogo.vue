<script setup lang="ts">
withDefaults(
  defineProps<{
    compact?: boolean
    size?: number
  }>(),
  { compact: false, size: 40 }
)
</script>

<template>
  <div class="app-logo" :class="{ compact }">
    <svg :width="size" :height="size" viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <path d="M24 3.5 41.5 13.7v20.6L24 44.5 6.5 34.3V13.7L24 3.5Z" fill="url(#argwsLogoFill)" fill-opacity=".16" stroke="url(#argwsLogoStroke)" stroke-width="2.6" />
      <path d="M16.8 17.2v13.6M16.8 21.5h8.4a6 6 0 0 1 6 6v3.3" stroke="#F8FAFC" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="16.8" cy="15.4" r="2.45" fill="#F8FAFC" />
      <circle cx="16.8" cy="32.7" r="2.45" fill="#F8FAFC" />
      <circle cx="31.2" cy="32.7" r="2.45" fill="#F8FAFC" />
      <defs>
        <linearGradient id="argwsLogoStroke" x1="8" y1="7" x2="41" y2="42" gradientUnits="userSpaceOnUse">
          <stop stop-color="#22D3EE" />
          <stop offset=".48" stop-color="#3B82F6" />
          <stop offset="1" stop-color="#A855F7" />
        </linearGradient>
        <linearGradient id="argwsLogoFill" x1="7" y1="6" x2="42" y2="43" gradientUnits="userSpaceOnUse">
          <stop stop-color="#22D3EE" />
          <stop offset=".55" stop-color="#6366F1" />
          <stop offset="1" stop-color="#A855F7" />
        </linearGradient>
      </defs>
    </svg>
    <div v-if="!compact" class="app-logo-copy">
      <strong>ARGWS</strong>
      <span>Git Monitor</span>
    </div>
  </div>
</template>

<style scoped>
.app-logo {
  display: inline-flex;
  align-items: center;
  gap: 0.68rem;
  min-width: 0;
}
.app-logo > svg {
  flex: 0 0 auto;
  filter: drop-shadow(0 0 10px color-mix(in srgb, var(--primary) 22%, transparent));
}
.app-logo-copy {
  display: flex;
  align-items: baseline;
  gap: 0.3rem;
  min-width: 0;
  line-height: 1;
  white-space: nowrap;
}
.app-logo-copy strong,
.app-logo-copy span {
  color: var(--text-strong);
  font-size: 1rem;
  font-weight: 780;
  letter-spacing: -0.025em;
}
.app-logo-copy strong { color: var(--text-strong); }
.app-logo-copy span { color: var(--text); font-weight: 660; }
.compact { justify-content: center; }
</style>
