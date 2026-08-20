<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps<{ page: number; pages: number; total: number }>()
const emit = defineEmits<{ change: [page: number] }>()

function change(target: number): void {
  if (target < 1 || target > props.pages || target === props.page) return
  emit('change', target)
}
</script>

<template>
  <footer v-if="pages > 1" class="pagination-bar">
    <span>{{ total }} registro(s)</span>
    <div>
      <button :disabled="page <= 1" aria-label="Página anterior" @click="change(page - 1)"><ChevronLeft :size="16" /></button>
      <strong>{{ page }}</strong><em>/</em><span>{{ pages }}</span>
      <button :disabled="page >= pages" aria-label="Próxima página" @click="change(page + 1)"><ChevronRight :size="16" /></button>
    </div>
  </footer>
</template>

<style scoped>
.pagination-bar { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.75rem 0.9rem; border-top: 1px solid var(--border-soft); }
.pagination-bar > span { color: var(--text-subtle); font-size: 0.62rem; }
.pagination-bar > div { display: flex; align-items: center; gap: 0.38rem; color: var(--text-muted); font-size: 0.64rem; }
.pagination-bar button { display: grid; place-items: center; width: 2rem; height: 2rem; color: var(--text-muted); border: 1px solid var(--border); border-radius: 0.55rem; background: var(--surface-raised); cursor: pointer; }
.pagination-bar button:disabled { cursor: not-allowed; opacity: 0.42; }
.pagination-bar strong { color: var(--text-strong); }
.pagination-bar em { color: var(--text-subtle); font-style: normal; }
</style>
