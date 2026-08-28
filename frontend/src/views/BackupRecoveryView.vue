<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Archive, CheckCircle2, Cloud, CloudCog, Copy, DatabaseBackup, FolderSync,
  HardDrive, Play, RefreshCw, RotateCcw, Server, ShieldCheck, Trash2, TriangleAlert
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'
import type { GitHubConnection, PaginatedResponse, Repository } from '../types/api'

type Tab = 'backups' | 'providers' | 'policies' | 'restore'
type ProviderKind = 's3' | 'minio' | 'dropbox' | 'google_drive' | 'sftp'

interface StorageProvider {
  id:string; name:string; kind:string; config:Record<string,unknown>; secret_hint:string|null;
  enabled:boolean; created_at:string; updated_at:string
}
interface StorageHubProvider {
  id:string; name:string; kind:string; storage_class:string; managed:boolean; role:string|null;
  bucket:string|null; base_path:string|null; enabled:boolean; secret_hint:string|null
}
interface StorageHubOverview {
  providers:StorageHubProvider[]
  stats:{snapshots:number;completed:number;failed:number;stored_bytes:number;last_status:string|null;last_at:string|null}
  internal_storage:{object_store:string;local_staging:string;deployment_manifest_required:boolean}
}
interface BackupPolicy {
  id:string; repository_id:string; provider_id:string; name:string; backup_type:string; branches:string[];
  include_releases:boolean; include_release_assets:boolean; include_lfs:boolean; include_submodules:boolean;
  schedule_kind:string; schedule_value:string|null; event_trigger:string|null; retention:Record<string,unknown>;
  enabled:boolean; last_run_at:string|null; next_run_at:string|null
}
interface BackupSnapshot {
  id:string; policy_id:string|null; repository_id:string; provider_id:string; job_id:string|null;
  backup_type:string; status:string; location:string|null; manifest:Record<string,unknown>;
  checksum_sha256:string|null; size_bytes:number|null; object_count:number|null; permanent:boolean;
  error:string|null; started_at:string|null; completed_at:string|null; created_at:string
}

const toasts = useToastStore()
const tab = ref<Tab>('backups')
const loading = ref(true)
const busy = ref('')
const repositories = ref<Repository[]>([])
const connections = ref<GitHubConnection[]>([])
const providers = ref<StorageProvider[]>([])
const policies = ref<BackupPolicy[]>([])
const backups = ref<BackupSnapshot[]>([])
const overview = ref<StorageHubOverview | null>(null)
const restorePreview = ref<Record<string, unknown> | null>(null)
const selectedSnapshotId = ref('')
const copyTargetProviderId = ref('')
const providerFormOpen = ref(false)

const providerForm = reactive({
  name:'', kind:'dropbox' as ProviderKind,
  endpoint_url:'', bucket:'argws-git-monitor', region:'us-east-1', prefix:'backups',
  base_path:'/ARGWS Git Monitor', folder_id:'', host:'', port:22, username:'', remote_path:'',
  access_key:'', secret_key:'', access_token:'', refresh_token:'', client_id:'', client_secret:'',
  private_key:'', known_hosts:''
})
const policyForm = reactive({
  repository_id:'', provider_id:'', name:'Backup diário', backup_type:'full', branches:'',
  include_releases:true, include_release_assets:true, include_lfs:true, include_submodules:true,
  schedule_kind:'daily', schedule_value:'', event_trigger:'', keep_last:10, keep_days:30
})
const manualForm = reactive({ repository_id:'', provider_id:'', backup_type:'full', branches:'', permanent:false })
const restoreForm = reactive({
  destination:'github_repository', connection_id:'', repository_full_name:'', new_repository_name:'',
  branch:'', restore_tags:true, restore_releases:true, target_path:'', confirmation:''
})

const repositoryMap = computed(() => Object.fromEntries(repositories.value.map((item) => [item.id, item.full_name])))
const providerMap = computed(() => Object.fromEntries(providers.value.map((item) => [item.id, item.name])))
const selectedBackup = computed(() => backups.value.find((item) => item.id === selectedSnapshotId.value) || null)
const hubProviders = computed(() => overview.value?.providers || [])
const internalProviders = computed(() => hubProviders.value.filter((item) => item.managed))
const externalProviders = computed(() => hubProviders.value.filter((item) => !item.managed))
const usableCopyTargets = computed(() => externalProviders.value.filter((item) => item.enabled))

function errorMessage(error:unknown):string { return error instanceof ApiError ? error.message : String(error) }
function size(value:number|null|undefined):string {
  if(!value)return '0 B'
  const units=['B','KB','MB','GB','TB'];let current=value;let index=0
  while(current>=1024&&index<units.length-1){current/=1024;index+=1}
  return `${current.toFixed(index?1:0)} ${units[index]}`
}
function when(value:string|null|undefined):string { return value ? new Date(value).toLocaleString('pt-BR') : '—' }
function statusClass(value:string):string {
  if(['completed','success'].includes(value))return 'ok'
  if(value.includes('warning'))return 'warn'
  if(['failed','cancelled'].includes(value))return 'bad'
  return 'info'
}
function providerLabel(kind:string):string {
  return ({s3:'Amazon S3',minio:'S3 / MinIO',dropbox:'Dropbox',google_drive:'Google Drive',sftp:'SFTP',local:'Interno'} as Record<string,string>)[kind] || kind
}
function resetProviderForm():void {
  Object.assign(providerForm,{name:'',kind:'dropbox',endpoint_url:'',bucket:'argws-git-monitor',region:'us-east-1',prefix:'backups',base_path:'/ARGWS Git Monitor',folder_id:'',host:'',port:22,username:'',remote_path:'',access_key:'',secret_key:'',access_token:'',refresh_token:'',client_id:'',client_secret:'',private_key:'',known_hosts:''})
}
async function loadRepositories():Promise<Repository[]> {
  const items:Repository[]=[];let page=1;let pages=1
  do{const response=await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100&monitoring_enabled=true`);items.push(...response.items);pages=response.pages;page+=1}while(page<=pages)
  return items
}
async function load():Promise<void> {
  loading.value=true
  try {
    const hub=await api.get<StorageHubOverview>('/storage-hub/overview')
    overview.value=hub
    const [repos,loadedConnections,loadedProviders,loadedPolicies,loadedBackups]=await Promise.all([
      loadRepositories(), api.get<GitHubConnection[]>('/github/connections'), api.get<StorageProvider[]>('/platform/storage-providers'),
      api.get<BackupPolicy[]>('/platform/backup-policies'), api.get<BackupSnapshot[]>('/platform/backups?limit=200')
    ])
    repositories.value=repos;connections.value=loadedConnections;providers.value=loadedProviders;policies.value=loadedPolicies;backups.value=loadedBackups
    const firstRepo=repos[0]?.id||''
    const preferred=hub.providers.find((item)=>item.storage_class==='internal_s3')?.id||loadedProviders[0]?.id||''
    if(!manualForm.repository_id)manualForm.repository_id=firstRepo
    if(!manualForm.provider_id)manualForm.provider_id=preferred
    if(!policyForm.repository_id)policyForm.repository_id=firstRepo
    if(!policyForm.provider_id)policyForm.provider_id=preferred
    if(!restoreForm.connection_id)restoreForm.connection_id=loadedConnections.find((item)=>item.status==='active')?.id||''
    if(!selectedSnapshotId.value&&loadedBackups.length)selectedSnapshotId.value=loadedBackups[0].id
    if(!copyTargetProviderId.value&&usableCopyTargets.value.length)copyTargetProviderId.value=usableCopyTargets.value[0].id
  } catch(error){toasts.error('Falha ao carregar Backup & Recovery',errorMessage(error))}
  finally{loading.value=false}
}
async function run(key:string,action:()=>Promise<void>):Promise<void>{busy.value=key;try{await action()}catch(error){toasts.error('Operação recusada',errorMessage(error))}finally{busy.value=''}}

function providerPayload():{config:Record<string,unknown>;secret:Record<string,unknown>} {
  if(providerForm.kind==='s3'||providerForm.kind==='minio')return {
    config:{endpoint_url:providerForm.endpoint_url||undefined,bucket:providerForm.bucket,region:providerForm.region,prefix:providerForm.prefix},
    secret:{access_key:providerForm.access_key,secret_key:providerForm.secret_key}
  }
  if(providerForm.kind==='dropbox')return {
    config:{base_path:providerForm.base_path,client_id:providerForm.client_id||undefined},
    secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}
  }
  if(providerForm.kind==='google_drive')return {
    config:{folder_id:providerForm.folder_id||undefined,client_id:providerForm.client_id||undefined},
    secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}
  }
  return {
    config:{host:providerForm.host,port:providerForm.port,username:providerForm.username,base_path:providerForm.remote_path,known_hosts:providerForm.known_hosts},
    secret:{private_key:providerForm.private_key}
  }
}
async function createProvider():Promise<void>{
  await run('provider-create',async()=>{
    const payload=providerPayload()
    const name=providerForm.name.trim()||providerLabel(providerForm.kind)
    const created=await api.post<StorageProvider>('/platform/storage-providers',{name,kind:providerForm.kind,config:payload.config,secret:payload.secret,enabled:true})
    toasts.success('Integração salva',`${created.name} foi cadastrada. Agora valide a conexão antes de usá-la.`)
    resetProviderForm();providerFormOpen.value=false;await load();tab.value='providers'
  })
}
async function testProvider(provider:StorageProvider|StorageHubProvider):Promise<void>{
  await run(`provider-${provider.id}`,async()=>{const result=await api.post<{ok:boolean;message:string}>(`/platform/storage-providers/${provider.id}/test`,{});result.ok?toasts.success('Provider operacional',result.message):toasts.error('Provider não validado',result.message)})
}
async function deleteProvider(provider:StorageHubProvider):Promise<void>{
  if(provider.managed)return
  if(!confirm(`Excluir ${provider.name}? Políticas vinculadas impedirão a exclusão.`))return
  await run(`provider-delete-${provider.id}`,async()=>{await api.delete(`/platform/storage-providers/${provider.id}`);toasts.success('Integração removida');await load()})
}
async function backupNow():Promise<void>{
  await run('backup-now',async()=>{
    const result=await api.post<{job_id:string;provider:{name:string}}>('/storage-hub/backups/run',{repository_id:manualForm.repository_id,provider_id:manualForm.provider_id||null,backup_type:manualForm.backup_type,branches:manualForm.branches.split(',').map(v=>v.trim()).filter(Boolean),permanent:manualForm.permanent})
    toasts.success('Backup validado e iniciado',`${result.provider.name} · Job ${result.job_id}`)
  })
}
async function copySnapshot(snapshot:BackupSnapshot):Promise<void>{
  if(!copyTargetProviderId.value)return
  await run(`copy-${snapshot.id}`,async()=>{const result=await api.post<{job_id:string}>(`/storage-hub/backups/${snapshot.id}/copy`,{provider_id:copyTargetProviderId.value});toasts.success('Cópia agendada',`Job ${result.job_id}. O SHA-256 será validado antes do envio.`)})
}
async function createPolicy():Promise<void>{
  await run('policy-create',async()=>{
    await api.post('/platform/backup-policies',{repository_id:policyForm.repository_id,provider_id:policyForm.provider_id,name:policyForm.name,backup_type:policyForm.backup_type,branches:policyForm.branches.split(',').map(v=>v.trim()).filter(Boolean),include_releases:policyForm.include_releases,include_release_assets:policyForm.include_release_assets,include_lfs:policyForm.include_lfs,include_submodules:policyForm.include_submodules,schedule_kind:policyForm.schedule_kind,schedule_value:policyForm.schedule_value||null,event_trigger:policyForm.event_trigger||null,retention:{keep_last:policyForm.keep_last,keep_days:policyForm.keep_days},enabled:true})
    toasts.success('Política criada','O scheduler avaliará esta política automaticamente.');await load()
  })
}
async function runPolicy(policy:BackupPolicy):Promise<void>{await run(`policy-${policy.id}`,async()=>{const result=await api.post<{job_id:string}>(`/platform/backup-policies/${policy.id}/run`,{});toasts.success('Backup enfileirado',`Job ${result.job_id}`)})}
async function retention(policy:BackupPolicy):Promise<void>{await run(`retention-${policy.id}`,async()=>{const result=await api.post<{deleted:number}>(`/platform/backup-policies/${policy.id}/apply-retention`,{});toasts.success('Retenção aplicada',`${result.deleted} snapshot(s) removido(s).`);await load()})}
async function previewRestore(snapshot:BackupSnapshot):Promise<void>{selectedSnapshotId.value=snapshot.id;tab.value='restore';await run('restore-preview',async()=>{restorePreview.value=await api.get<Record<string,unknown>>(`/platform/backups/${snapshot.id}/restore-preview`);restoreForm.confirmation=`RESTAURAR ${snapshot.id}`})}
async function restore(simulate:boolean):Promise<void>{
  if(!selectedBackup.value)return
  await run(simulate?'restore-sim':'restore',async()=>{
    const body={...restoreForm,connection_id:restoreForm.connection_id||null,repository_full_name:restoreForm.repository_full_name||null,new_repository_name:restoreForm.new_repository_name||null,branch:restoreForm.branch||null,target_path:restoreForm.target_path||null,simulate,confirmation:simulate?null:restoreForm.confirmation}
    const result=await api.post<Record<string,unknown>>(`/platform/backups/${selectedBackup.value!.id}/restore`,body)
    simulate?(restorePreview.value=result,toasts.success('Simulação concluída','Nenhuma alteração foi realizada.')):toasts.success('Restore enfileirado',`Job ${String(result.job_id||'criado')}`)
  })
}

onMounted(load)
</script>

<template>
  <div class="page-stack backup-page">
    <section class="hero-panel backup-hero">
      <div>
        <span class="eyebrow">BACKUP & RECOVERY</span>
        <h2>Proteção de repositórios sem configuração frágil</h2>
        <p>O Git Monitor mantém storage interno pronto para uso. Faça o primeiro backup sem cadastrar nuvem e depois replique snapshots validados para Dropbox, Google Drive, S3/MinIO ou SFTP.</p>
        <div class="button-row hero-actions"><button class="button primary" :disabled="!repositories.length||busy==='backup-now'" @click="tab='backups'"><DatabaseBackup :size="16"/>Novo backup</button><button class="button secondary" @click="tab='providers'"><CloudCog :size="16"/>Integrações</button><RouterLink class="button ghost" to="/backup-complete"><Archive :size="16"/>Backup completo + exclusão</RouterLink></div>
      </div>
      <div class="metric-grid hero-metrics">
        <article class="metric-card"><span>Snapshots</span><strong>{{overview?.stats.snapshots||0}}</strong><small>{{overview?.stats.completed||0}} concluído(s)</small></article>
        <article class="metric-card"><span>Falhas</span><strong>{{overview?.stats.failed||0}}</strong><small>histórico registrado</small></article>
        <article class="metric-card"><span>Armazenado</span><strong>{{size(overview?.stats.stored_bytes)}}</strong><small>snapshots concluídos</small></article>
        <article class="metric-card"><span>Último backup</span><strong class="last-status">{{overview?.stats.last_status||'—'}}</strong><small>{{when(overview?.stats.last_at)}}</small></article>
      </div>
    </section>

    <nav class="segmented-tabs" aria-label="Backup e Recovery">
      <button :class="{active:tab==='backups'}" @click="tab='backups'"><DatabaseBackup :size="15"/>Backups</button>
      <button :class="{active:tab==='providers'}" @click="tab='providers'"><Cloud :size="15"/>Storage & Nuvem</button>
      <button :class="{active:tab==='policies'}" @click="tab='policies'"><ShieldCheck :size="15"/>Políticas</button>
      <button :class="{active:tab==='restore'}" @click="tab='restore'"><RotateCcw :size="15"/>Restore</button>
      <button class="refresh-tab" :disabled="loading" @click="load"><RefreshCw :size="14"/>Atualizar</button>
    </nav>

    <template v-if="tab==='backups'">
      <section class="internal-grid">
        <article v-for="provider in internalProviders" :key="provider.id" class="provider-card internal-card">
          <header><div><span class="provider-icon"><Server v-if="provider.storage_class==='internal_s3'" :size="18"/><HardDrive v-else :size="18"/></span><div><h4>{{provider.name}}</h4><p>{{provider.storage_class==='internal_s3'?'Object store interno em estrutura bucket/key':'Staging local persistente para recovery e integrações'}}</p></div></div><span class="status-pill ok"><CheckCircle2 :size="12"/>Gerenciado</span></header>
          <div class="provider-meta"><span v-if="provider.bucket">Bucket <strong>{{provider.bucket}}</strong></span><span>Classe <strong>{{provider.storage_class}}</strong></span></div>
          <button class="button ghost compact" :disabled="busy===`provider-${provider.id}`" @click="testProvider(provider)"><ShieldCheck :size="14"/>Testar armazenamento</button>
        </article>
      </section>

      <section class="panel backup-now-panel">
        <header><div><strong>Executar backup agora</strong><span>O destino é testado antes do job entrar na fila. O S3 interno gerenciado já fica disponível sem configuração externa.</span></div><DatabaseBackup :size="20"/></header>
        <div class="backup-form-grid">
          <label class="field"><span>Repositório</span><select v-model="manualForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label>
          <label class="field"><span>Destino</span><select v-model="manualForm.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}} · {{providerLabel(provider.kind)}}</option></select></label>
          <label class="field"><span>Conteúdo</span><select v-model="manualForm.backup_type"><option value="full">Completo / mirror</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Somente releases</option></select></label>
        </div>
        <label v-if="manualForm.backup_type==='selected_branches'" class="field branches-field"><span>Branches ou padrões</span><input v-model="manualForm.branches" placeholder="main, develop, release/*"/></label>
        <div class="action-toolbar"><label class="check"><input v-model="manualForm.permanent" type="checkbox"/>Preservar snapshot da retenção automática</label><button class="button primary" :disabled="busy==='backup-now'||!manualForm.repository_id" @click="backupNow"><Play :size="15"/>Validar e iniciar backup</button></div>
      </section>

      <section v-if="usableCopyTargets.length" class="info-callout"><FolderSync :size="19"/><div><strong>Replicação para nuvem disponível</strong><p>Escolha um destino e use “Copiar” em qualquer snapshot concluído. A origem é validada por SHA-256 antes do envio.</p></div></section>
      <label v-if="usableCopyTargets.length" class="field copy-target"><span>Destino padrão para cópia</span><select v-model="copyTargetProviderId"><option v-for="provider in usableCopyTargets" :key="provider.id" :value="provider.id">{{provider.name}} · {{providerLabel(provider.kind)}}</option></select></label>

      <section class="panel table-panel desktop-table"><header><div><strong>Snapshots</strong><span>Integridade, origem, tamanho, data e ações de recuperação.</span></div></header><div class="table-wrap"><table><thead><tr><th>Repositório</th><th>Destino</th><th>Status</th><th>Tamanho</th><th>SHA-256</th><th>Data</th><th>Ações</th></tr></thead><tbody>
        <tr v-for="item in backups" :key="item.id"><td><strong>{{repositoryMap[item.repository_id]||item.repository_id}}</strong><small>{{item.backup_type}}</small></td><td>{{providerMap[item.provider_id]||item.provider_id}}</td><td><span class="status-pill" :class="statusClass(item.status)">{{item.status}}</span></td><td>{{size(item.size_bytes)}}</td><td><code>{{item.checksum_sha256?.slice(0,14)||'—'}}</code></td><td>{{when(item.completed_at||item.created_at)}}</td><td><div class="row-actions"><button class="button ghost compact" @click="previewRestore(item)"><RotateCcw :size="13"/>Restore</button><button v-if="usableCopyTargets.length&&item.location&&item.status.startsWith('completed')" class="button ghost compact" :disabled="busy===`copy-${item.id}`" @click="copySnapshot(item)"><Copy :size="13"/>Copiar</button></div></td></tr>
        <tr v-if="!backups.length&&!loading"><td colspan="7" class="empty">Nenhum snapshot criado ainda.</td></tr>
      </tbody></table></div></section>

      <div class="mobile-cards">
        <article v-for="item in backups" :key="item.id" class="resource-card"><div class="resource-card-head"><div><strong>{{repositoryMap[item.repository_id]||item.repository_id}}</strong><small>{{providerMap[item.provider_id]||item.provider_id}} · {{item.backup_type}}</small></div><span class="status-pill" :class="statusClass(item.status)">{{item.status}}</span></div><div class="snapshot-meta"><span>Tamanho<strong>{{size(item.size_bytes)}}</strong></span><span>SHA-256<strong>{{item.checksum_sha256?.slice(0,14)||'—'}}</strong></span><span>Data<strong>{{when(item.completed_at||item.created_at)}}</strong></span></div><div class="button-row"><button class="button secondary" @click="previewRestore(item)"><RotateCcw :size="14"/>Restaurar</button><button v-if="usableCopyTargets.length&&item.location&&item.status.startsWith('completed')" class="button ghost" :disabled="busy===`copy-${item.id}`" @click="copySnapshot(item)"><Copy :size="14"/>Copiar</button></div></article>
      </div>
    </template>

    <template v-else-if="tab==='providers'">
      <section class="panel provider-intro"><header><div><strong>Storage interno sempre disponível</strong><span>Não é necessário cadastrar Dropbox, Drive ou S3 externo para o backup básico funcionar.</span></div><HardDrive :size="20"/></header><div class="provider-grid"><article v-for="provider in internalProviders" :key="provider.id" class="provider-card"><header><div><h4>{{provider.name}}</h4><p>{{provider.storage_class==='internal_s3'?'Bucket interno persistente, isolado por usuário.':'Área local persistente usada para staging e recovery.'}}</p></div><span class="status-pill ok">Ativo</span></header><div class="provider-meta"><span>Tipo <strong>{{provider.storage_class}}</strong></span><span v-if="provider.bucket">Bucket <strong>{{provider.bucket}}</strong></span></div></article></div></section>

      <section class="panel"><header><div><strong>Integrações externas</strong><span>Use-as para redundância e distribuição. Credenciais ficam criptografadas no backend.</span></div><button class="button primary compact" @click="providerFormOpen=!providerFormOpen"><CloudCog :size="14"/>Adicionar integração</button></header>
        <div v-if="externalProviders.length" class="provider-grid providers-list"><article v-for="provider in externalProviders" :key="provider.id" class="provider-card"><header><div><h4>{{provider.name}}</h4><p>{{providerLabel(provider.kind)}} · {{provider.secret_hint||'credencial protegida'}}</p></div><span class="status-pill" :class="provider.enabled?'ok':'bad'">{{provider.enabled?'Ativo':'Inativo'}}</span></header><div class="button-row"><button class="button secondary compact" :disabled="busy===`provider-${provider.id}`" @click="testProvider(provider)"><ShieldCheck :size="14"/>Testar</button><button class="button ghost compact danger-text" :disabled="busy===`provider-delete-${provider.id}`" @click="deleteProvider(provider)"><Trash2 :size="14"/>Excluir</button></div></article></div>
        <div v-else class="empty-provider"><Cloud :size="24"/><strong>Nenhuma nuvem externa cadastrada</strong><p>Seu backup interno continua funcionando normalmente. Adicione nuvem somente quando quiser redundância.</p></div>
      </section>

      <section v-if="providerFormOpen" class="panel provider-wizard"><header><div><strong>Nova integração de armazenamento</strong><span>Campos específicos por provider, sem JSON manual.</span></div><CloudCog :size="20"/></header>
        <div class="provider-kind-grid"><button v-for="kind in (['dropbox','google_drive','s3','minio','sftp'] as ProviderKind[])" :key="kind" class="kind-card" :class="{active:providerForm.kind===kind}" @click="providerForm.kind=kind"><Cloud v-if="kind!=='sftp'" :size="18"/><Server v-else :size="18"/><strong>{{providerLabel(kind)}}</strong></button></div>
        <label class="field"><span>Nome amigável</span><input v-model="providerForm.name" :placeholder="`Ex.: ${providerLabel(providerForm.kind)} produção`"/></label>
        <div v-if="providerForm.kind==='s3'||providerForm.kind==='minio'" class="form-grid"><label class="field"><span>Endpoint {{providerForm.kind==='s3'?'opcional':'S3/MinIO'}}</span><input v-model="providerForm.endpoint_url" placeholder="https://s3.example.com"/></label><label class="field"><span>Bucket</span><input v-model="providerForm.bucket"/></label><label class="field"><span>Região</span><input v-model="providerForm.region"/></label><label class="field"><span>Prefixo</span><input v-model="providerForm.prefix"/></label><label class="field"><span>Access Key</span><input v-model="providerForm.access_key" autocomplete="off"/></label><label class="field"><span>Secret Key</span><input v-model="providerForm.secret_key" type="password" autocomplete="new-password"/></label></div>
        <template v-else-if="providerForm.kind==='dropbox'||providerForm.kind==='google_drive'"><div class="info-callout oauth-help"><ShieldCheck :size="18"/><div><strong>OAuth recomendado</strong><p>Use refresh token + client ID + client secret para conexão durável. Access token isolado também é aceito para testes.</p></div></div><div class="form-grid"><label v-if="providerForm.kind==='dropbox'" class="field"><span>Pasta base</span><input v-model="providerForm.base_path"/></label><label v-else class="field"><span>Folder ID opcional</span><input v-model="providerForm.folder_id"/></label><label class="field"><span>Access Token opcional</span><input v-model="providerForm.access_token" type="password" autocomplete="new-password"/></label><label class="field"><span>Refresh Token</span><input v-model="providerForm.refresh_token" type="password" autocomplete="new-password"/></label><label class="field"><span>Client ID</span><input v-model="providerForm.client_id"/></label><label class="field"><span>Client Secret</span><input v-model="providerForm.client_secret" type="password" autocomplete="new-password"/></label></div></template>
        <div v-else class="form-grid"><label class="field"><span>Host</span><input v-model="providerForm.host"/></label><label class="field"><span>Porta</span><input v-model.number="providerForm.port" type="number"/></label><label class="field"><span>Usuário</span><input v-model="providerForm.username"/></label><label class="field"><span>Diretório remoto</span><input v-model="providerForm.remote_path"/></label><label class="field full-row"><span>Chave privada</span><textarea v-model="providerForm.private_key" rows="5"/></label><label class="field full-row"><span>Known hosts</span><textarea v-model="providerForm.known_hosts" rows="3"/></label></div>
        <div class="button-row wizard-actions"><button class="button primary" :disabled="busy==='provider-create'" @click="createProvider"><Cloud :size="15"/>Salvar integração</button><button class="button ghost" @click="providerFormOpen=false">Cancelar</button></div>
      </section>
    </template>

    <template v-else-if="tab==='policies'">
      <section class="panel"><header><div><strong>Nova política de backup</strong><span>Agendamento e retenção independentes por repositório.</span></div><ShieldCheck :size="20"/></header><div class="form-grid policy-grid"><label class="field"><span>Nome</span><input v-model="policyForm.name"/></label><label class="field"><span>Repositório</span><select v-model="policyForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label class="field"><span>Destino</span><select v-model="policyForm.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}}</option></select></label><label class="field"><span>Tipo</span><select v-model="policyForm.backup_type"><option value="full">Completo</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Releases</option></select></label><label class="field"><span>Agendamento</span><select v-model="policyForm.schedule_kind"><option value="manual">Manual</option><option value="interval_hours">A cada X horas</option><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option><option value="event">Após evento</option></select></label><label class="field"><span>Valor / Evento</span><select v-if="policyForm.schedule_kind==='event'" v-model="policyForm.event_trigger"><option value="release">Release</option><option value="push">Push</option><option value="workflow_success">Workflow com sucesso</option></select><input v-else v-model="policyForm.schedule_value" placeholder="Ex.: 6 para intervalo"/></label></div><label v-if="policyForm.backup_type==='selected_branches'" class="field"><span>Branches/padrões</span><input v-model="policyForm.branches" placeholder="main, develop, release/*"/></label><div class="checks"><label class="check"><input v-model="policyForm.include_releases" type="checkbox"/>Releases</label><label class="check"><input v-model="policyForm.include_release_assets" type="checkbox"/>Assets</label><label class="check"><input v-model="policyForm.include_lfs" type="checkbox"/>Git LFS</label><label class="check"><input v-model="policyForm.include_submodules" type="checkbox"/>Submodules</label></div><div class="retention-grid"><label class="field"><span>Manter últimos</span><input v-model.number="policyForm.keep_last" type="number" min="0"/></label><label class="field"><span>Manter por dias</span><input v-model.number="policyForm.keep_days" type="number" min="0"/></label></div><button class="button primary" :disabled="busy==='policy-create'||!policyForm.repository_id||!policyForm.provider_id" @click="createPolicy">Criar política</button></section>
      <section class="card-list"><article v-for="item in policies" :key="item.id" class="resource-card policy-card"><div class="resource-card-head"><div><strong>{{item.name}}</strong><small>{{repositoryMap[item.repository_id]||item.repository_id}} · {{providerMap[item.provider_id]||item.provider_id}}</small></div><span class="status-pill" :class="item.enabled?'ok':'bad'">{{item.enabled?'Ativa':'Inativa'}}</span></div><div class="policy-meta"><span>{{item.backup_type}}</span><span>{{item.schedule_kind}}{{item.schedule_value?` · ${item.schedule_value}`:''}}</span><span>Último: {{when(item.last_run_at)}}</span></div><div class="button-row"><button class="button primary compact" :disabled="busy===`policy-${item.id}`" @click="runPolicy(item)"><Play :size="13"/>Executar</button><button class="button ghost compact" :disabled="busy===`retention-${item.id}`" @click="retention(item)"><Trash2 :size="13"/>Aplicar retenção</button></div></article><div v-if="!policies.length&&!loading" class="resource-card empty-provider">Nenhuma política criada.</div></section>
    </template>

    <template v-else>
      <section v-if="!backups.length" class="panel empty-provider"><RotateCcw :size="26"/><strong>Nenhum snapshot disponível</strong><p>Crie um backup antes de usar a recuperação.</p></section>
      <template v-else><section class="panel restore-panel"><header><div><strong>Plano de restauração</strong><span>Selecione um snapshot e simule antes da execução real.</span></div><RotateCcw :size="20"/></header><label class="field"><span>Snapshot</span><select v-model="selectedSnapshotId"><option v-for="item in backups" :key="item.id" :value="item.id">{{repositoryMap[item.repository_id]||item.repository_id}} · {{when(item.completed_at||item.created_at)}} · {{item.status}}</option></select></label><div class="form-grid"><label class="field"><span>Destino</span><select v-model="restoreForm.destination"><option value="github_repository">Repositório GitHub existente</option><option value="new_github_repository">Novo repositório GitHub</option><option value="local">Diretório local</option><option value="sftp">Servidor SFTP</option></select></label><label v-if="restoreForm.destination.includes('github')" class="field"><span>Conexão GitHub</span><select v-model="restoreForm.connection_id"><option v-for="connection in connections.filter(c=>c.status==='active')" :key="connection.id" :value="connection.id">@{{connection.github_login}} · {{connection.name}}</option></select></label><label v-if="restoreForm.destination==='github_repository'" class="field"><span>owner/repo</span><input v-model="restoreForm.repository_full_name" placeholder="wkarts/projeto"/></label><label v-if="restoreForm.destination==='new_github_repository'" class="field"><span>Novo nome</span><input v-model="restoreForm.new_repository_name"/></label><label v-if="restoreForm.destination==='local'||restoreForm.destination==='sftp'" class="field"><span>Caminho</span><input v-model="restoreForm.target_path"/></label><label class="field"><span>Branch opcional</span><input v-model="restoreForm.branch"/></label></div><div class="checks"><label class="check"><input v-model="restoreForm.restore_tags" type="checkbox"/>Restaurar tags</label><label class="check"><input v-model="restoreForm.restore_releases" type="checkbox"/>Restaurar releases suportadas</label></div><div class="button-row"><button class="button secondary" :disabled="busy==='restore-preview'" @click="selectedBackup&&previewRestore(selectedBackup)"><ShieldCheck :size="14"/>Inspecionar snapshot</button><button class="button secondary" :disabled="busy==='restore-sim'" @click="restore(true)">Simular restore</button></div></section>
        <section v-if="restorePreview" class="panel preview-panel"><header><div><strong>Prévia / dry-run</strong><span>Revise o plano antes de executar.</span></div><CheckCircle2 :size="20"/></header><pre class="code-block">{{JSON.stringify(restorePreview,null,2)}}</pre></section>
        <section class="panel danger-restore"><header><div><strong>Executar restauração</strong><span>Confirmação explícita necessária para qualquer alteração real.</span></div><TriangleAlert :size="20"/></header><label class="field"><span>Confirmação</span><input v-model="restoreForm.confirmation" :placeholder="selectedBackup?`RESTAURAR ${selectedBackup.id}`:''"/></label><button class="button danger" :disabled="busy==='restore'||!selectedBackup" @click="restore(false)"><RotateCcw :size="15"/>Executar restore</button></section></template>
    </template>
  </div>
</template>

<style scoped>
.backup-hero{align-items:center}.hero-actions{margin-top:1rem}.hero-metrics{align-self:stretch}.last-status{font-size:.82rem!important;overflow-wrap:anywhere}.refresh-tab{margin-left:auto}.internal-grid{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}.internal-card{border-color:color-mix(in srgb,var(--success) 26%,var(--border))}.provider-card header>div:first-child{display:flex;gap:.55rem;min-width:0}.provider-icon{display:grid;place-items:center;flex:none;width:2rem;height:2rem;border-radius:.6rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.provider-meta{display:flex;gap:.7rem;flex-wrap:wrap;color:var(--text-muted);font-size:.61rem}.provider-meta span{display:grid;gap:.1rem}.provider-meta strong{color:var(--text-strong);font-size:.64rem}.backup-now-panel{display:grid;gap:.8rem}.backup-form-grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:.75rem}.branches-field{max-width:720px}.check,.checks{display:flex;align-items:center;gap:.45rem;color:var(--text-muted);font-size:.66rem}.checks{flex-wrap:wrap;gap:.8rem}.check input{accent-color:var(--primary)}.copy-target{max-width:460px}.row-actions{display:flex;gap:.25rem;flex-wrap:wrap}.snapshot-meta{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem}.snapshot-meta span{display:grid;gap:.1rem;color:var(--text-muted);font-size:.59rem}.snapshot-meta strong{overflow-wrap:anywhere;color:var(--text-strong);font-size:.64rem}.table-wrap td strong,.table-wrap td small{display:block}.table-wrap td small{margin-top:.15rem;color:var(--text-subtle);font-size:.6rem}.table-wrap td,.table-wrap th{padding:.72rem;font-size:.66rem;border-bottom:1px solid var(--border-soft);text-align:left;vertical-align:top}.table-wrap th{color:var(--text-muted);font-size:.57rem;text-transform:uppercase;letter-spacing:.06em}.table-wrap code{font-size:.61rem}.provider-intro,.provider-wizard{display:grid;gap:.85rem}.providers-list{margin-top:.8rem}.empty-provider{display:grid;place-items:center;gap:.2rem;min-height:130px;text-align:center;color:var(--text-muted)}.empty-provider strong{color:var(--text-strong);font-size:.75rem}.empty-provider p{max-width:520px;margin:0;font-size:.65rem;line-height:1.5}.provider-kind-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem}.kind-card{display:flex;align-items:center;justify-content:center;gap:.4rem;min-height:3rem;padding:.55rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.75rem;background:var(--surface-raised);font-size:.65rem;cursor:pointer}.kind-card.active{color:var(--text-strong);border-color:var(--primary);background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem}.full-row{grid-column:1/-1}.oauth-help{margin:.2rem 0}.wizard-actions{margin-top:.1rem}.policy-grid{margin:.8rem 0}.retention-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;max-width:440px;margin:.75rem 0}.policy-card{grid-template-columns:1fr}.policy-meta{display:flex;gap:.4rem;flex-wrap:wrap}.policy-meta span{padding:.2rem .4rem;border:1px solid var(--border-soft);border-radius:.45rem;color:var(--text-muted);background:var(--surface-soft);font-size:.6rem}.restore-panel,.preview-panel,.danger-restore{display:grid;gap:.8rem}.danger-restore{border-color:color-mix(in srgb,var(--danger) 28%,var(--border))}.empty{text-align:center;color:var(--text-muted);padding:1.5rem}
@media(max-width:1100px){.backup-form-grid{grid-template-columns:1fr 1fr}.backup-form-grid .field:first-child{grid-column:1/-1}.provider-kind-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:820px){.internal-grid,.backup-form-grid,.form-grid{grid-template-columns:1fr}.backup-form-grid .field:first-child,.full-row{grid-column:auto}.provider-kind-grid{grid-template-columns:1fr 1fr}.action-toolbar{align-items:stretch}.action-toolbar .button{width:100%}.snapshot-meta{grid-template-columns:1fr 1fr}}@media(max-width:560px){.internal-grid,.provider-kind-grid,.retention-grid{grid-template-columns:1fr}.snapshot-meta{grid-template-columns:1fr}.checks{align-items:flex-start;flex-direction:column}.refresh-tab{margin-left:0}}
</style>
