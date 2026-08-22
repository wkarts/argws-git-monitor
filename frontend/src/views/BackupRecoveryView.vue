<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Archive, CheckCircle2, Cloud, DatabaseBackup, HardDrive, Play, RefreshCw, RotateCcw, ShieldCheck, Trash2 } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'
import type { PaginatedResponse, Repository } from '../types/api'

type Tab = 'backups' | 'policies' | 'providers' | 'restore'
interface StorageProvider { id:string; name:string; kind:string; config:Record<string,unknown>; secret_hint:string|null; enabled:boolean; created_at:string; updated_at:string }
interface BackupPolicy { id:string; repository_id:string; provider_id:string; name:string; backup_type:string; branches:string[]; include_releases:boolean; include_release_assets:boolean; include_lfs:boolean; include_submodules:boolean; schedule_kind:string; schedule_value:string|null; event_trigger:string|null; retention:Record<string,unknown>; enabled:boolean; last_run_at:string|null; next_run_at:string|null }
interface BackupSnapshot { id:string; policy_id:string|null; repository_id:string; provider_id:string; job_id:string|null; backup_type:string; status:string; location:string|null; manifest:Record<string,unknown>; checksum_sha256:string|null; size_bytes:number|null; object_count:number|null; permanent:boolean; error:string|null; started_at:string|null; completed_at:string|null; created_at:string }

const toasts = useToastStore()
const tab = ref<Tab>('backups')
const loading = ref(true)
const busy = ref('')
const repositories = ref<Repository[]>([])
const providers = ref<StorageProvider[]>([])
const policies = ref<BackupPolicy[]>([])
const backups = ref<BackupSnapshot[]>([])
const restorePreview = ref<Record<string, unknown> | null>(null)
const selectedSnapshotId = ref('')

const providerForm = reactive({ name:'Armazenamento local', kind:'local', configText:'{"base_path":"/data/backups"}', secretText:'{}' })
const policyForm = reactive({ repository_id:'', provider_id:'', name:'Backup diário', backup_type:'full', branches:'', include_releases:true, include_release_assets:true, include_lfs:true, include_submodules:true, schedule_kind:'daily', schedule_value:'', event_trigger:'', keep_last:10, keep_days:30 })
const manualForm = reactive({ repository_id:'', provider_id:'', backup_type:'full', branches:'', permanent:false })
const restoreForm = reactive({ destination:'github_repository', connection_id:'', repository_full_name:'', new_repository_name:'', branch:'', restore_tags:true, restore_releases:true, target_path:'', confirmation:'' })

const repositoryMap = computed(() => Object.fromEntries(repositories.value.map((item) => [item.id, item.full_name])))
const providerMap = computed(() => Object.fromEntries(providers.value.map((item) => [item.id, item.name])))
const selectedBackup = computed(() => backups.value.find((item) => item.id === selectedSnapshotId.value) || null)

function errorMessage(error: unknown): string { return error instanceof ApiError ? error.message : String(error) }
function jsonObject(value:string): Record<string, unknown> {
  const parsed = JSON.parse(value || '{}') as unknown
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('Informe um objeto JSON válido.')
  return parsed as Record<string, unknown>
}
function size(value:number|null):string {
  if (!value) return '—'
  const units=['B','KB','MB','GB','TB']; let current=value; let index=0
  while(current>=1024 && index<units.length-1){current/=1024;index+=1}
  return `${current.toFixed(index ? 1 : 0)} ${units[index]}`
}
function when(value:string|null):string { return value ? new Date(value).toLocaleString('pt-BR') : '—' }
function statusClass(value:string):string { return ['completed','success'].includes(value) ? 'ok' : value.includes('warning') ? 'warn' : value==='failed' ? 'bad' : 'run' }

async function loadRepositories():Promise<Repository[]> {
  const items:Repository[]=[]; let page=1; let pages=1
  do { const response=await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100`); items.push(...response.items); pages=response.pages; page+=1 } while(page<=pages)
  return items
}
async function load():Promise<void> {
  loading.value=true
  try {
    const [repos, loadedProviders, loadedPolicies, loadedBackups] = await Promise.all([
      loadRepositories(), api.get<StorageProvider[]>('/platform/storage-providers'), api.get<BackupPolicy[]>('/platform/backup-policies'), api.get<BackupSnapshot[]>('/platform/backups?limit=200')
    ])
    repositories.value=repos; providers.value=loadedProviders; policies.value=loadedPolicies; backups.value=loadedBackups
    const firstRepo=repos[0]?.id || ''; const firstProvider=loadedProviders[0]?.id || ''
    if(!manualForm.repository_id) manualForm.repository_id=firstRepo
    if(!manualForm.provider_id) manualForm.provider_id=firstProvider
    if(!policyForm.repository_id) policyForm.repository_id=firstRepo
    if(!policyForm.provider_id) policyForm.provider_id=firstProvider
    if(!selectedSnapshotId.value && loadedBackups.length) selectedSnapshotId.value=loadedBackups[0].id
  } catch(error){ toasts.error('Falha ao carregar Backup & Recovery', errorMessage(error)) }
  finally{ loading.value=false }
}
async function run(key:string, action:()=>Promise<void>):Promise<void>{ busy.value=key; try{await action()}catch(error){toasts.error('Operação recusada',errorMessage(error))}finally{busy.value=''} }

async function createProvider():Promise<void>{
  await run('provider-create', async()=>{
    const created=await api.post<StorageProvider>('/platform/storage-providers',{name:providerForm.name,kind:providerForm.kind,config:jsonObject(providerForm.configText),secret:jsonObject(providerForm.secretText),enabled:true})
    toasts.success('Provider salvo', `${created.name} foi cadastrado; o secret não será retornado.`); providerForm.secretText='{}'; await load(); tab.value='providers'
  })
}
async function testProvider(provider:StorageProvider):Promise<void>{
  await run(`provider-${provider.id}`, async()=>{ const result=await api.post<{ok:boolean;message:string}>(`/platform/storage-providers/${provider.id}/test`,{}); result.ok ? toasts.success('Provider operacional',result.message) : toasts.error('Provider não validado',result.message) })
}
async function deleteProvider(provider:StorageProvider):Promise<void>{
  if(!confirm(`Excluir o provider ${provider.name}? Políticas vinculadas impedirão a exclusão.`)) return
  await run(`provider-delete-${provider.id}`, async()=>{await api.delete(`/platform/storage-providers/${provider.id}`);toasts.success('Provider removido');await load()})
}
async function createPolicy():Promise<void>{
  await run('policy-create', async()=>{
    await api.post('/platform/backup-policies',{repository_id:policyForm.repository_id,provider_id:policyForm.provider_id,name:policyForm.name,backup_type:policyForm.backup_type,branches:policyForm.branches.split(',').map(v=>v.trim()).filter(Boolean),include_releases:policyForm.include_releases,include_release_assets:policyForm.include_release_assets,include_lfs:policyForm.include_lfs,include_submodules:policyForm.include_submodules,schedule_kind:policyForm.schedule_kind,schedule_value:policyForm.schedule_value||null,event_trigger:policyForm.event_trigger||null,retention:{keep_last:policyForm.keep_last,keep_days:policyForm.keep_days},enabled:true})
    toasts.success('Política criada','O scheduler do worker passa a avaliá-la automaticamente.');await load()
  })
}
async function runPolicy(policy:BackupPolicy):Promise<void>{ await run(`policy-${policy.id}`,async()=>{const result=await api.post<{job_id:string}>(`/platform/backup-policies/${policy.id}/run`,{});toasts.success('Backup enfileirado',`Job ${result.job_id}`)}) }
async function retention(policy:BackupPolicy):Promise<void>{ await run(`retention-${policy.id}`,async()=>{const result=await api.post<{deleted:number}>(`/platform/backup-policies/${policy.id}/apply-retention`,{});toasts.success('Retenção aplicada',`${result.deleted} snapshot(s) removido(s) conforme a política.`);await load()}) }
async function backupNow():Promise<void>{
  await run('backup-now',async()=>{const result=await api.post<{job_id:string}>('/platform/backups/run',{repository_id:manualForm.repository_id,provider_id:manualForm.provider_id,backup_type:manualForm.backup_type,branches:manualForm.branches.split(',').map(v=>v.trim()).filter(Boolean),permanent:manualForm.permanent});toasts.success('Backup iniciado',`Job ${result.job_id}. Acompanhe na Fila.`)})
}
async function previewRestore(snapshot:BackupSnapshot):Promise<void>{
  selectedSnapshotId.value=snapshot.id;tab.value='restore';await run('restore-preview',async()=>{restorePreview.value=await api.get<Record<string,unknown>>(`/platform/backups/${snapshot.id}/restore-preview`);restoreForm.confirmation=`RESTAURAR ${snapshot.id}`})
}
async function restore(simulate:boolean):Promise<void>{
  if(!selectedBackup.value)return
  await run(simulate?'restore-sim':'restore',async()=>{
    const body={...restoreForm,connection_id:restoreForm.connection_id||null,repository_full_name:restoreForm.repository_full_name||null,new_repository_name:restoreForm.new_repository_name||null,branch:restoreForm.branch||null,target_path:restoreForm.target_path||null,simulate,confirmation:simulate?null:restoreForm.confirmation}
    const result=await api.post<Record<string,unknown>>(`/platform/backups/${selectedBackup.value!.id}/restore`,body)
    simulate ? (restorePreview.value=result,toasts.success('Simulação concluída','Nenhuma alteração foi realizada.')) : toasts.success('Restore enfileirado',`Job ${String(result.job_id||'criado')}`)
  })
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div><span class="eyebrow">PROTEÇÃO E RECUPERAÇÃO</span><h2>Backup & Recovery</h2><p>Backups Git verificáveis, múltiplos providers, retenção segura e restauração com simulação obrigatória.</p></div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
    </section>

    <nav class="tabs" aria-label="Backup e Recovery">
      <button :class="{active:tab==='backups'}" @click="tab='backups'"><DatabaseBackup :size="16"/>Backups</button>
      <button :class="{active:tab==='policies'}" @click="tab='policies'"><ShieldCheck :size="16"/>Policies</button>
      <button :class="{active:tab==='providers'}" @click="tab='providers'"><Cloud :size="16"/>Storage Providers</button>
      <button :class="{active:tab==='restore'}" @click="tab='restore'"><RotateCcw :size="16"/>Restore</button>
    </nav>

    <template v-if="tab==='backups'">
      <section class="panel">
        <header><div><strong>Backup Now</strong><span>Executa no worker e registra progresso real na Fila.</span></div></header>
        <div class="grid cols-3">
          <label class="field"><span>Repositório</span><select v-model="manualForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label>
          <label class="field"><span>Provider</span><select v-model="manualForm.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}} · {{provider.kind}}</option></select></label>
          <label class="field"><span>Tipo</span><select v-model="manualForm.backup_type"><option value="full">Completo / mirror</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Somente releases</option></select></label>
        </div>
        <label v-if="manualForm.backup_type==='selected_branches'" class="field"><span>Branches/padrões</span><input v-model="manualForm.branches" placeholder="main, develop, release/*"/></label>
        <label class="check"><input v-model="manualForm.permanent" type="checkbox"/> Marcar snapshot como permanente</label>
        <button class="button primary" :disabled="busy==='backup-now'||!manualForm.repository_id||!manualForm.provider_id" @click="backupNow"><Play :size="15"/>Backup Now</button>
      </section>

      <section class="panel table-panel"><header><div><strong>Snapshots</strong><span>Manifesto, checksum, tamanho, status e destino.</span></div></header>
        <div class="table-wrap"><table><thead><tr><th>Repositório</th><th>Tipo</th><th>Status</th><th>Tamanho</th><th>Checksum</th><th>Data</th><th></th></tr></thead><tbody>
          <tr v-for="item in backups" :key="item.id"><td>{{repositoryMap[item.repository_id]||item.repository_id}}</td><td>{{item.backup_type}}</td><td><span class="status" :class="statusClass(item.status)">{{item.status}}</span></td><td>{{size(item.size_bytes)}}</td><td><code>{{item.checksum_sha256?.slice(0,12)||'—'}}</code></td><td>{{when(item.completed_at||item.created_at)}}</td><td><button class="button ghost" @click="previewRestore(item)">Restaurar</button></td></tr>
          <tr v-if="!backups.length"><td colspan="7" class="empty">Nenhum backup executado.</td></tr>
        </tbody></table></div>
      </section>
    </template>

    <template v-else-if="tab==='policies'">
      <section class="panel"><header><div><strong>Nova política</strong><span>Cada repositório possui agenda e retenção independentes.</span></div></header>
        <div class="grid cols-3"><label class="field"><span>Nome</span><input v-model="policyForm.name"/></label><label class="field"><span>Repositório</span><select v-model="policyForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label class="field"><span>Provider</span><select v-model="policyForm.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}}</option></select></label></div>
        <div class="grid cols-3"><label class="field"><span>Tipo</span><select v-model="policyForm.backup_type"><option value="full">Completo</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Releases</option></select></label><label class="field"><span>Agendamento</span><select v-model="policyForm.schedule_kind"><option value="manual">Manual</option><option value="interval_hours">A cada X horas</option><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option><option value="event">Após evento</option></select></label><label class="field"><span>Valor / Evento</span><template v-if="policyForm.schedule_kind==='event'"><select v-model="policyForm.event_trigger"><option value="release">Release</option><option value="push">Push</option><option value="workflow_success">Workflow com sucesso</option></select></template><input v-else v-model="policyForm.schedule_value" placeholder="Ex.: 6 para interval_hours"/></label></div>
        <label v-if="policyForm.backup_type==='selected_branches'" class="field"><span>Branches/padrões</span><input v-model="policyForm.branches" placeholder="main, develop, release/*"/></label>
        <div class="checks"><label class="check"><input v-model="policyForm.include_releases" type="checkbox"/>Releases</label><label class="check"><input v-model="policyForm.include_release_assets" type="checkbox"/>Assets</label><label class="check"><input v-model="policyForm.include_lfs" type="checkbox"/>Git LFS</label><label class="check"><input v-model="policyForm.include_submodules" type="checkbox"/>Submodules</label></div>
        <div class="grid cols-2"><label class="field"><span>Manter últimos</span><input v-model.number="policyForm.keep_last" type="number" min="0"/></label><label class="field"><span>Manter por dias</span><input v-model.number="policyForm.keep_days" type="number" min="0"/></label></div>
        <button class="button primary" :disabled="busy==='policy-create'" @click="createPolicy"><ShieldCheck :size="15"/>Criar política</button>
      </section>
      <section class="cards"><article v-for="policy in policies" :key="policy.id" class="card"><header><div><strong>{{policy.name}}</strong><span>{{repositoryMap[policy.repository_id]||policy.repository_id}}</span></div><span class="status ok" v-if="policy.enabled">ativa</span></header><p>{{policy.backup_type}} · {{policy.schedule_kind}}<template v-if="policy.event_trigger"> · {{policy.event_trigger}}</template></p><small>Última: {{when(policy.last_run_at)}} · Provider: {{providerMap[policy.provider_id]||policy.provider_id}}</small><div class="actions"><button class="button secondary" @click="runPolicy(policy)"><Play :size="14"/>Executar</button><button class="button ghost" @click="retention(policy)">Aplicar retenção</button></div></article></section>
    </template>

    <template v-else-if="tab==='providers'">
      <section class="panel"><header><div><strong>Novo Storage Provider</strong><span>Secrets são criptografados e depois retornam apenas mascarados.</span></div></header>
        <div class="grid cols-2"><label class="field"><span>Nome</span><input v-model="providerForm.name"/></label><label class="field"><span>Tipo</span><select v-model="providerForm.kind"><option value="local">Local</option><option value="s3">S3</option><option value="minio">MinIO</option><option value="google_drive">Google Drive</option><option value="dropbox">Dropbox</option><option value="sftp">SFTP/VPS</option></select></label></div>
        <div class="grid cols-2"><label class="field"><span>Configuração JSON</span><textarea v-model="providerForm.configText" class="code"/></label><label class="field"><span>Secret JSON</span><textarea v-model="providerForm.secretText" class="code" placeholder="Nunca será devolvido integralmente"/></label></div>
        <button class="button primary" :disabled="busy==='provider-create'" @click="createProvider"><Cloud :size="15"/>Salvar provider</button>
      </section>
      <section class="cards"><article v-for="provider in providers" :key="provider.id" class="card"><header><div><strong>{{provider.name}}</strong><span>{{provider.kind}}</span></div><HardDrive :size="18"/></header><p>Secret: <code>{{provider.secret_hint||'não informado'}}</code></p><div class="actions"><button class="button secondary" @click="testProvider(provider)"><CheckCircle2 :size="14"/>Testar</button><button class="button ghost danger" @click="deleteProvider(provider)"><Trash2 :size="14"/>Excluir</button></div></article></section>
    </template>

    <template v-else>
      <section class="panel"><header><div><strong>Restore Center</strong><span>Primeiro simule. A execução real valida SHA-256 e exige confirmação textual.</span></div><Archive :size="20"/></header>
        <label class="field"><span>Snapshot</span><select v-model="selectedSnapshotId" @change="restorePreview=null"><option v-for="item in backups" :key="item.id" :value="item.id">{{repositoryMap[item.repository_id]}} · {{item.backup_type}} · {{when(item.created_at)}}</option></select></label>
        <div class="grid cols-2"><label class="field"><span>Destino</span><select v-model="restoreForm.destination"><option value="github_repository">Repositório GitHub existente</option><option value="new_github_repository">Novo repositório GitHub</option><option value="local">Diretório local do worker</option><option value="sftp">SFTP (via Deployment Target)</option></select></label><label class="field"><span>Branch específica (opcional)</span><input v-model="restoreForm.branch"/></label></div>
        <div v-if="restoreForm.destination.includes('github')" class="grid cols-2"><label class="field"><span>Connection ID</span><input v-model="restoreForm.connection_id" placeholder="UUID da conexão GitHub"/></label><label v-if="restoreForm.destination==='github_repository'" class="field"><span>owner/repo de destino</span><input v-model="restoreForm.repository_full_name"/></label><label v-else class="field"><span>Novo repositório</span><input v-model="restoreForm.new_repository_name"/></label></div>
        <label v-if="restoreForm.destination==='local'" class="field"><span>Diretório de destino</span><input v-model="restoreForm.target_path" placeholder="/data/restores/projeto"/></label>
        <div class="checks"><label class="check"><input v-model="restoreForm.restore_tags" type="checkbox"/>Restaurar tags</label><label class="check"><input v-model="restoreForm.restore_releases" type="checkbox"/>Restaurar releases/assets</label></div>
        <div class="actions"><button class="button secondary" :disabled="busy==='restore-sim'||!selectedSnapshotId" @click="restore(true)">Simular restauração</button><button class="button primary" :disabled="busy==='restore'||!restorePreview" @click="restore(false)"><RotateCcw :size="15"/>Executar restore</button></div>
        <label v-if="restorePreview" class="field danger-zone"><span>Confirmação da execução</span><input v-model="restoreForm.confirmation"/><small>A restauração real só é aceita depois da simulação e da confirmação exata.</small></label>
        <pre v-if="restorePreview" class="preview">{{JSON.stringify(restorePreview,null,2)}}</pre>
      </section>
    </template>
  </div>
</template>

<style scoped>
.tabs{display:flex;gap:.35rem;overflow:auto;padding:.35rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface)}.tabs button{display:flex;align-items:center;gap:.4rem;white-space:nowrap;padding:.58rem .75rem;color:var(--text-muted);border-radius:.62rem;background:transparent;cursor:pointer}.tabs button.active{color:var(--text-strong);background:var(--surface-raised);box-shadow:inset 0 0 0 1px var(--border)}.panel,.card{border:1px solid var(--border);border-radius:.9rem;background:var(--surface);box-shadow:var(--shadow-sm)}.panel{padding:1rem}.panel>header,.card>header{display:flex;align-items:center;justify-content:space-between;gap:.7rem;margin-bottom:.8rem}.panel header div,.card header div{display:grid}.panel header span,.card header span,.card small{color:var(--text-muted);font-size:.67rem}.grid{display:grid;gap:.75rem}.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.checks,.actions{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;margin:.7rem 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:.8rem}.card{padding:.85rem}.card p{margin:.4rem 0;color:var(--text)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.72rem}th,td{padding:.65rem;border-bottom:1px solid var(--border-soft);text-align:left;white-space:nowrap}th{color:var(--text-muted)}.status{display:inline-flex;padding:.18rem .42rem;border-radius:999px;font-size:.58rem;font-weight:800}.status.ok{color:var(--success);background:color-mix(in srgb,var(--success) 10%,transparent)}.status.warn{color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,transparent)}.status.bad{color:var(--danger);background:color-mix(in srgb,var(--danger) 10%,transparent)}.status.run{color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 10%,transparent)}.code,.preview{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.code{min-height:9rem}.preview{max-height:28rem;overflow:auto;padding:.8rem;color:var(--text);border:1px solid var(--border);border-radius:.7rem;background:var(--surface-raised);font-size:.68rem}.danger-zone{margin-top:.9rem;padding:.75rem;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:.7rem}.danger{color:var(--danger)!important}.empty{text-align:center;color:var(--text-muted)}@media(max-width:820px){.cols-2,.cols-3{grid-template-columns:1fr}.panel{padding:.8rem}.cards{grid-template-columns:1fr}}
</style>
