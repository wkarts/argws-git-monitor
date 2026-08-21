<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  AlertTriangle, Archive, Database, Download, FileClock, FileText, Filter, HardDrive,
  RefreshCw, Search, Server, ShieldCheck, Trash2
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { formatDateTime, formatRelative } from '../services/format'
import { useToastStore } from '../stores/toast'
import type { AuditLogItem, LogLine, LogPurgeResult, LogSource, LogTailResponse } from '../types/api'

const toasts = useToastStore()
const sources = ref<LogSource[]>([])
const selectedSource = ref('api')
const tail = ref<LogTailResponse | null>(null)
const audit = ref<AuditLogItem[]>([])
const tab = ref<'runtime' | 'audit'>('runtime')
const query = ref('')
const level = ref('')
const lineLimit = ref(500)
const autoRefresh = ref(true)
const loading = ref(true)
const downloading = ref(false)
const auditQuery = ref('')
let timer: number | undefined

const selected = computed(() => sources.value.find((item) => item.key === selectedSource.value) || null)
const totalBytes = computed(() => sources.value.reduce((sum, item) => sum + item.size_bytes, 0))
const availableCount = computed(() => sources.value.filter((item) => item.available).length)
const filteredAudit = computed(() => {
  const term = auditQuery.value.trim().toLowerCase()
  if (!term) return audit.value
  return audit.value.filter((item) =>
    [item.action, item.user_name, item.user_email, item.entity_type, item.entity_id, item.ip_address]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term))
  )
})

function humanBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / (1024 ** index)
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`
}

function sourceIcon(source: LogSource) {
  if (source.category === 'Infraestrutura') return Database
  if (source.category === 'Web') return Server
  return FileText
}

function levelClass(line: LogLine): string {
  const normalized = (line.level || '').toLowerCase()
  if (['error', 'critical', 'fatal'].includes(normalized)) return 'danger'
  if (['warning', 'warn'].includes(normalized)) return 'warning'
  if (normalized === 'debug') return 'muted'
  return 'info'
}

async function loadSources(): Promise<void> {
  sources.value = await api.get<LogSource[]>('/admin/logs/sources')
  if (!sources.value.some((item) => item.key === selectedSource.value)) {
    selectedSource.value = sources.value[0]?.key || 'api'
  }
}

async function loadTail(silent = false): Promise<void> {
  if (!selectedSource.value) return
  if (!silent) loading.value = true
  try {
    const params = new URLSearchParams({ lines: String(lineLimit.value) })
    if (query.value.trim()) params.set('q', query.value.trim())
    if (level.value) params.set('level', level.value)
    tail.value = await api.get<LogTailResponse>(`/admin/logs/tail/${selectedSource.value}?${params}`)
  } catch (error) {
    if (!silent) toasts.error('Falha ao consultar logs', error instanceof ApiError ? error.message : undefined)
  } finally { if (!silent) loading.value = false }
}

async function loadAudit(): Promise<void> {
  loading.value = true
  try { audit.value = await api.get<AuditLogItem[]>('/admin/logs/audit?limit=1000') }
  catch (error) { toasts.error('Falha ao consultar auditoria', error instanceof ApiError ? error.message : undefined) }
  finally { loading.value = false }
}

async function refreshAll(silent = false): Promise<void> {
  try {
    await loadSources()
    if (tab.value === 'runtime') await loadTail(silent)
    else await loadAudit()
  } catch (error) {
    if (!silent) toasts.error('Central de logs indisponível', error instanceof ApiError ? error.message : undefined)
  }
}

function selectSource(key: string): void {
  selectedSource.value = key
  tab.value = 'runtime'
  void loadTail()
}

function setTab(value: 'runtime' | 'audit'): void {
  tab.value = value
  value === 'audit' ? void loadAudit() : void loadTail()
}

function saveDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

async function downloadStack(): Promise<void> {
  downloading.value = true
  try {
    const result = await api.download('/admin/logs/download')
    saveDownload(result.blob, result.filename || 'argws-git-monitor-logs.zip')
    toasts.success('Pacote de logs gerado')
  } catch (error) { toasts.error('Falha no download', error instanceof ApiError ? error.message : undefined) }
  finally { downloading.value = false }
}

async function downloadAudit(): Promise<void> {
  downloading.value = true
  try {
    const result = await api.download('/admin/logs/audit/download')
    saveDownload(result.blob, result.filename || 'argws-git-monitor-audit.csv')
  } catch (error) { toasts.error('Falha no download', error instanceof ApiError ? error.message : undefined) }
  finally { downloading.value = false }
}

async function purge(): Promise<void> {
  const daysText = window.prompt('Remover somente arquivos de log rotacionados mais antigos que quantos dias?', '30')
  if (!daysText) return
  const days = Number(daysText)
  if (!Number.isFinite(days) || days < 1) { toasts.warning('Período inválido'); return }
  const confirmation = window.prompt('A operação preserva o arquivo de log atual. Digite exatamente: PURGAR LOGS')
  if (confirmation !== 'PURGAR LOGS') return
  try {
    const result = await api.post<LogPurgeResult>('/admin/logs/purge', {
      older_than_days: Math.floor(days), confirmation
    })
    toasts.success('Retenção aplicada', `${result.deleted_files} arquivo(s) removido(s), ${humanBytes(result.reclaimed_bytes)} liberados.`)
    await refreshAll()
  } catch (error) { toasts.error('Falha na retenção', error instanceof ApiError ? error.message : undefined) }
}

onMounted(() => {
  void refreshAll()
  timer = window.setInterval(() => {
    if (autoRefresh.value && tab.value === 'runtime') void refreshAll(true)
  }, 5000)
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div class="page-stack logs-page">
    <section class="page-heading">
      <div><span class="eyebrow">OBSERVABILIDADE DA STACK</span><h2>Central de logs</h2><p>Aplicação, workers, Nginx, PostgreSQL, Redis, RabbitMQ e trilha de auditoria em uma interface única.</p></div>
      <div class="button-row"><button class="button secondary" :disabled="downloading" @click="downloadStack"><Download :size="16" />Baixar stack</button><button class="button ghost danger-text" @click="purge"><Trash2 :size="16" />Retenção</button></div>
    </section>

    <section class="log-metrics">
      <article><HardDrive :size="19" /><div><strong>{{ humanBytes(totalBytes) }}</strong><span>armazenados em ./data-logs</span></div></article>
      <article><Server :size="19" /><div><strong>{{ availableCount }}/{{ sources.length }}</strong><span>fontes com arquivos</span></div></article>
      <article><RefreshCw :size="19" /><div><strong>{{ autoRefresh ? '5 s' : 'manual' }}</strong><span>atualização do painel</span></div></article>
      <article><ShieldCheck :size="19" /><div><strong>{{ audit.length || '—' }}</strong><span>eventos de auditoria carregados</span></div></article>
    </section>

    <section class="log-source-grid">
      <button v-for="source in sources" :key="source.key" :class="['source-card',{active: selectedSource===source.key && tab==='runtime'}]" @click="selectSource(source.key)">
        <component :is="sourceIcon(source)" :size="18" /><div><strong>{{ source.label }}</strong><span>{{ source.category }} · {{ source.file_count }} arquivo(s)</span><small>{{ humanBytes(source.size_bytes) }} · {{ formatRelative(source.last_modified_at) }}</small></div><i :class="{ available: source.available }" />
      </button>
      <button :class="['source-card audit-card',{active:tab==='audit'}]" @click="setTab('audit')"><FileClock :size="18" /><div><strong>Auditoria de usuários</strong><span>Banco de dados · ações administrativas</span><small>login, segurança e operações</small></div><i class="available" /></button>
    </section>

    <section v-if="tab==='runtime'" class="log-console">
      <header>
        <div><span class="eyebrow">{{ selected?.category || 'LOG' }}</span><h3>{{ selected?.label || selectedSource }}</h3><small>{{ tail?.files.join(', ') || 'Nenhum arquivo disponível' }}</small></div>
        <div class="console-actions"><label class="auto-toggle"><input v-model="autoRefresh" type="checkbox" />Auto-refresh</label><button class="icon-button" @click="loadTail()"><RefreshCw :size="16" /></button></div>
      </header>
      <div class="log-toolbar"><label><Search :size="15" /><input v-model="query" placeholder="Pesquisar texto, endpoint, erro, request id…" @keyup.enter="loadTail()" /></label><label><Filter :size="15" /><select v-model="level" @change="loadTail()"><option value="">Todos os níveis</option><option value="DEBUG">DEBUG</option><option value="INFO">INFO</option><option value="WARNING">WARNING</option><option value="ERROR">ERROR</option><option value="CRITICAL">CRITICAL</option></select></label><select v-model.number="lineLimit" @change="loadTail()"><option :value="200">200 linhas</option><option :value="500">500 linhas</option><option :value="1000">1.000 linhas</option><option :value="5000">5.000 linhas</option><option :value="10000">10.000 linhas</option></select><button class="button secondary compact" @click="loadTail()">Aplicar</button></div>
      <div v-if="loading" class="log-loading"><span class="skeleton" v-for="n in 8" :key="n" /></div>
      <div v-else-if="!tail?.lines.length" class="log-empty"><AlertTriangle :size="24" /><strong>Nenhuma linha encontrada</strong><p>A fonte pode ainda não ter gerado arquivo, ou os filtros não encontraram correspondência.</p></div>
      <div v-else class="log-lines"><article v-for="(line,index) in tail.lines" :key="`${line.file}-${index}`" :class="levelClass(line)"><time>{{ line.timestamp ? formatDateTime(line.timestamp) : '—' }}</time><span class="level">{{ line.level || 'LOG' }}</span><code>{{ line.message }}</code><small>{{ line.file }}</small></article></div>
    </section>

    <section v-else class="audit-panel">
      <header><div><span class="eyebrow">TRILHA DE AUDITORIA</span><h3>Ações de usuários e administradores</h3></div><button class="button secondary compact" :disabled="downloading" @click="downloadAudit"><Download :size="15" />Baixar CSV</button></header>
      <label class="audit-search"><Search :size="16" /><input v-model="auditQuery" placeholder="Buscar ação, usuário, IP, entidade…" /></label>
      <div v-if="loading" class="log-loading"><span class="skeleton" v-for="n in 6" :key="n" /></div>
      <div v-else-if="!filteredAudit.length" class="log-empty"><Archive :size="24" /><strong>Nenhum evento encontrado</strong></div>
      <div v-else class="audit-list"><article v-for="item in filteredAudit" :key="item.id"><div class="audit-icon"><ShieldCheck :size="16" /></div><div><strong>{{ item.action }}</strong><span>{{ item.user_name || 'Sistema' }}<template v-if="item.user_email"> · {{ item.user_email }}</template></span><small>{{ item.entity_type || 'evento' }}<template v-if="item.entity_id"> · {{ item.entity_id }}</template> · {{ item.ip_address || 'IP não informado' }} · {{ formatDateTime(item.created_at) }}</small></div><details v-if="Object.keys(item.details || {}).length"><summary>detalhes</summary><pre>{{ JSON.stringify(item.details,null,2) }}</pre></details></article></div>
    </section>
  </div>
</template>

<style scoped>
.log-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem}.log-metrics article{display:flex;align-items:center;gap:.65rem;padding:.85rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface);box-shadow:var(--shadow-sm);color:var(--primary-strong)}.log-metrics article>div{display:grid}.log-metrics strong{color:var(--text-strong);font-size:1rem}.log-metrics span{color:var(--text-muted);font-size:.61rem}.log-source-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem}.source-card{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.55rem;padding:.75rem;color:var(--text-muted);text-align:left;border:1px solid var(--border);border-radius:.8rem;background:var(--surface);cursor:pointer;box-shadow:var(--shadow-sm)}.source-card:hover,.source-card.active{color:var(--primary-strong);border-color:color-mix(in srgb,var(--primary) 42%,var(--border));background:color-mix(in srgb,var(--primary) 5%,var(--surface))}.source-card>div{display:grid;min-width:0}.source-card strong{overflow:hidden;color:var(--text-strong);font-size:.68rem;text-overflow:ellipsis;white-space:nowrap}.source-card span,.source-card small{overflow:hidden;color:var(--text-muted);font-size:.55rem;text-overflow:ellipsis;white-space:nowrap}.source-card i{width:.5rem;height:.5rem;border-radius:50%;background:var(--text-subtle)}.source-card i.available{background:var(--success);box-shadow:0 0 0 4px color-mix(in srgb,var(--success) 9%,transparent)}.audit-card{grid-column:auto}.log-console,.audit-panel{overflow:hidden;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.log-console>header,.audit-panel>header{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.85rem 1rem;border-bottom:1px solid var(--border-soft)}.log-console h3,.audit-panel h3{margin:.05rem 0;color:var(--text-strong)}.log-console header small{color:var(--text-subtle);font-size:.56rem}.console-actions{display:flex;align-items:center;gap:.5rem}.auto-toggle{display:flex;align-items:center;gap:.35rem;color:var(--text-muted);font-size:.62rem}.log-toolbar{display:grid;grid-template-columns:1.5fr .7fr auto auto;gap:.5rem;padding:.65rem;border-bottom:1px solid var(--border-soft);background:var(--surface-soft)}.log-toolbar label,.audit-search{display:flex;align-items:center;gap:.4rem;padding:0 .6rem;border:1px solid var(--border);border-radius:.6rem;background:var(--surface)}.log-toolbar input,.log-toolbar select,.audit-search input{width:100%;min-height:2.2rem;color:var(--text);border:0;outline:0;background:transparent;font:inherit;font-size:.66rem}.log-toolbar>select{min-height:2.2rem;color:var(--text);border:1px solid var(--border);border-radius:.6rem;background:var(--surface);padding:0 .5rem}.log-lines{max-height:62vh;overflow:auto;background:color-mix(in srgb,var(--background) 88%,#000 12%);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.log-lines article{display:grid;grid-template-columns:160px 70px minmax(0,1fr) 130px;gap:.65rem;padding:.3rem .65rem;border-bottom:1px solid color-mix(in srgb,var(--border) 50%,transparent);font-size:.58rem}.log-lines time,.log-lines small{color:var(--text-subtle)}.log-lines .level{color:var(--info);font-weight:800}.log-lines code{white-space:pre-wrap;word-break:break-word;color:var(--text)}.log-lines article.warning .level{color:var(--warning)}.log-lines article.danger .level{color:var(--danger)}.log-lines article.muted{opacity:.68}.log-loading{display:grid;gap:.2rem;padding:.65rem}.log-loading span{height:28px}.log-empty{display:grid;place-items:center;gap:.4rem;padding:4rem 1rem;color:var(--text-muted);text-align:center}.log-empty strong{color:var(--text-strong)}.log-empty p{margin:0;font-size:.68rem}.audit-search{margin:.7rem}.audit-list{display:grid;max-height:62vh;overflow:auto}.audit-list article{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.65rem;padding:.7rem 1rem;border-top:1px solid var(--border-soft)}.audit-icon{display:grid;place-items:center;width:2rem;height:2rem;color:var(--primary-strong);border-radius:.6rem;background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.audit-list article>div:nth-child(2){display:grid}.audit-list strong{color:var(--text-strong);font-size:.68rem}.audit-list span{color:var(--text-muted);font-size:.61rem}.audit-list small{color:var(--text-subtle);font-size:.56rem}.audit-list details{max-width:400px}.audit-list summary{color:var(--primary-strong);font-size:.58rem;cursor:pointer}.audit-list pre{max-width:400px;max-height:180px;overflow:auto;padding:.5rem;border-radius:.5rem;background:var(--surface-soft);color:var(--text);font-size:.55rem}.danger-text{color:var(--danger)!important}
@media(max-width:1200px){.log-source-grid{grid-template-columns:repeat(3,1fr)}.log-metrics{grid-template-columns:repeat(2,1fr)}}@media(max-width:800px){.log-source-grid{grid-template-columns:repeat(2,1fr)}.log-toolbar{grid-template-columns:1fr 1fr}.log-lines article{grid-template-columns:100px 60px 1fr}.log-lines small{grid-column:3}.audit-list article{grid-template-columns:auto 1fr}.audit-list details{grid-column:2;max-width:none}}@media(max-width:560px){.log-metrics,.log-source-grid,.log-toolbar{grid-template-columns:1fr}.log-console>header,.audit-panel>header{align-items:stretch;flex-direction:column}.console-actions{justify-content:space-between}.log-lines article{grid-template-columns:1fr;gap:.15rem;padding:.55rem}.log-lines small{grid-column:auto}.audit-list article{grid-template-columns:auto 1fr}.audit-list details{grid-column:1/-1}.page-heading .button-row{width:100%;display:grid;grid-template-columns:1fr 1fr}.page-heading .button{width:100%}}
</style>
