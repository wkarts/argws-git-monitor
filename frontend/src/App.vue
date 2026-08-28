<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import DialogHost from './components/DialogHost.vue'
import ToastHost from './components/ToastHost.vue'
import UpdatePrompt from './components/UpdatePrompt.vue'
import { useThemeStore } from './stores/theme'

const theme = useThemeStore()
onMounted(() => theme.initialize())
</script>

<template>
  <RouterView />
  <ToastHost />
  <DialogHost />
  <UpdatePrompt />
</template>
