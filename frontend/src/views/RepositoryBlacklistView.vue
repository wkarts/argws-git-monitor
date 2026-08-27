<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Ban, RefreshCw, RotateCcw } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'

interface BlacklistItem {
  repository_id: string
  github_id: number
  full_name: string
  connection_id: string
  connection_name: string
  blacklisted_at: string | null
  reason: string | null
}

const toasts = useToastStore()
const loading = ref(true)
const items = ref<BlacklistItem[]>([])
const busy = ref('')

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString('pt-BR') : '—'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    items.value = await api.get<BlacklistItem[]>('/repository-controls/blacklist')
  } catch (error) {
    toasts.error('Falha ao carregar lista negra', error instanceof ApiError ? error.message : undefined)
  } finally {
    loading.value = false
  }
}

async function restore(item: BlacklistItem): Promise<void> {
  if (!window.confirm(`Remover ${item.full_name} da lista negra e voltar a monitorá-lo?`)) return
  busy.value = item.repository_id
  try {
    await api.delete(`/repository-controls/${item.repository_id}/blacklist`)
    toasts.success('Repositório reativado', `${item.full_name} voltou ao monitoramento.`)
    await load()
  } catch (error) {
    toasts.error('Falha ao reativar', error instanceof ApiError ? error.message : undefined)
  } finally {
    busy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">EXCLUSÃO PERSISTENTE</span>
        <h2>Lista negra de repositórios</h2>
        <p>Itens desta lista não aparecem no monitor e não são reimportados automaticamente nas sincronizações.</p>
      </div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
    </section>

    <section class="panel table-panel">
      <header>
        <div><strong>Ignorados permanentemente</strong><span>{{ items.length }} repositório(s)</span></div>
      </header>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Repositório</th><th>Conexão</th><th>Motivo</th><th>Desde</th><th></th></tr></thead>
          <tbody>
            <tr v-for="item in items" :key="item.repository_id">
              <td><strong>{{ item.full_name }}</strong><small>#{{ item.github_id }}</small></td>
              <td>{{ item.connection_name }}</td>
              <td>{{ item.reason || 'Ignorado pelo usuário.' }}</td>
              <td>{{ when(item.blacklisted_at) }}</td>
              <td><button class="button ghost compact" :disabled="busy===item.repository_id" @click="restore(item)"><RotateCcw :size="14"/>Restaurar ao monitor</button></td>
            </tr>
            <tr v-if="!loading && !items.length"><td colspan="5" class="empty"><Ban :size="20"/>Nenhum repositório na lista negra.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.table-panel{overflow:hidden}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:.8rem;text-align:left;border-bottom:1px solid var(--border-soft);font-size:.72rem}th{color:var(--text-muted);font-size:.62rem;text-transform:uppercase;letter-spacing:.06em}td strong,td small{display:block}td strong{color:var(--text-strong)}td small{margin-top:.2rem;color:var(--text-subtle)}.empty{text-align:center;color:var(--text-muted);padding:2rem}.empty svg{vertical-align:middle;margin-right:.35rem}
</style>
