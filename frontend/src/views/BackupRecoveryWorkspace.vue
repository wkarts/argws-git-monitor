<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Archive, Cloud, CloudCog, Copy, DatabaseBackup, FolderPlus,
  FolderSync, HardDrive, Play, RefreshCw, RotateCcw, Server, ShieldCheck,
  Trash2, TriangleAlert
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import { useToastStore } from '../stores/toast'
import type { GitHubConnection, PaginatedResponse, Repository } from '../types/api'

type Tab = 'backups' | 'storage' | 'policies' | 'restore'
type ProviderKind = 's3' | 'minio' | 'dropbox' | 'google_drive' | 'sftp'

interface StorageProvider {
  id:string; name:string; kind:string; config:Record<string,unknown>; secret_hint:string|null;
  enabled:boolean; created_at:string; updated_at:string
}
interface HubProvider {
  id:string; name:string; kind:string; storage_class:string; managed:boolean; system_default:boolean;
  role:string|null; bucket:string|null; bucket_alias:string|null; base_path:string|null; enabled:boolean;
  secret_hint:string|null; available:boolean|null; has_objects:boolean|null; storage_error:string|null
}
interface StorageHubOverview {
  providers:HubProvider[]
  stats:{snapshots:number;completed:number;failed:number;stored_bytes:number;last_status:string|null;last_at:string|null;repositories:number}
  internal_storage:{object_store:string;engine:string;available:boolean;error:string|null;endpoint:string|null;local_staging:string;deployment_manifest_required:boolean}
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
const storageLoadError = ref('')
const repositoryLoadError = ref('')
const providerFormOpen = ref(false)
const selectedSnapshotId = ref('')
const copyTargetProviderId = ref('')
const restorePreview = ref<Record<string,unknown>|null>(null)
const bucketName = ref('projetos')
let realtimeTimer:number|undefined

const manualForm = reactive({repository_id:'',provider_id:'',backup_type:'full',branches:'',permanent:false})
const policyForm = reactive({repository_id:'',provider_id:'',name:'Backup diário',backup_type:'full',branches:'',include_releases:true,include_release_assets:true,include_lfs:true,include_submodules:true,schedule_kind:'daily',schedule_value:'',event_trigger:'',keep_last:10,keep_days:30})
const restoreForm = reactive({destination:'github_repository',connection_id:'',repository_full_name:'',new_repository_name:'',branch:'',restore_tags:true,restore_releases:true,target_path:'',confirmation:''})
const providerForm = reactive({name:'',kind:'dropbox' as ProviderKind,endpoint_url:'',bucket:'argws-git-monitor',region:'us-east-1',prefix:'backups',base_path:'/ARGWS Git Monitor',folder_id:'',host:'',port:22,username:'',remote_path:'',access_key:'',secret_key:'',access_token:'',refresh_token:'',client_id:'',client_secret:'',private_key:'',known_hosts:''})

const repositoryMap = computed(()=>Object.fromEntries(repositories.value.map(item=>[item.id,item.full_name])))
const providerMap = computed(()=>Object.fromEntries(providers.value.map(item=>[item.id,item.name])))
const hubProviders = computed(()=>overview.value?.providers||[])
const internalBuckets = computed(()=>hubProviders.value.filter(item=>item.managed&&item.storage_class==='internal_s3'))
const localStorage = computed(()=>hubProviders.value.find(item=>item.managed&&item.storage_class==='internal_local')||null)
const externalProviders = computed(()=>hubProviders.value.filter(item=>!item.managed))
const selectedBackup = computed(()=>backups.value.find(item=>item.id===selectedSnapshotId.value)||null)
const usableCopyTargets = computed(()=>externalProviders.value.filter(item=>item.enabled))
const minioAvailable = computed(()=>overview.value?.internal_storage.available===true)

function message(error:unknown):string{return error instanceof ApiError?error.message:String(error)}
function size(value:number|null|undefined):string{if(!value)return'0 B';const units=['B','KB','MB','GB','TB'];let n=value,i=0;while(n>=1024&&i<units.length-1){n/=1024;i+=1}return`${n.toFixed(i?1:0)} ${units[i]}`}
function when(value:string|null|undefined):string{return value?new Date(value).toLocaleString('pt-BR'):'—'}
function providerLabel(kind:string):string{return({s3:'Amazon S3',minio:'S3 / MinIO',dropbox:'Dropbox',google_drive:'Google Drive',sftp:'SFTP',local:'Local'} as Record<string,string>)[kind]||kind}
function statusClass(value:string):string{if(['completed','success'].includes(value))return'ok';if(value.includes('warning'))return'warn';if(['failed','cancelled'].includes(value))return'bad';return'info'}

async function loadRepositories():Promise<Repository[]>{const items:Repository[]=[];let page=1,pages=1;do{const response=await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100&monitoring_enabled=true`);items.push(...response.items);pages=response.pages;page+=1}while(page<=pages);return items}

function assignDefaults():void{
  const firstRepo=repositories.value[0]?.id||''
  const preferred=providers.value.find(item=>(item.config||{}).storage_class==='internal_s3')?.id||providers.value[0]?.id||''
  if(!manualForm.repository_id||!repositories.value.some(item=>item.id===manualForm.repository_id))manualForm.repository_id=firstRepo
  if(!manualForm.provider_id||!providers.value.some(item=>item.id===manualForm.provider_id))manualForm.provider_id=preferred
  if(!policyForm.repository_id||!repositories.value.some(item=>item.id===policyForm.repository_id))policyForm.repository_id=firstRepo
  if(!policyForm.provider_id||!providers.value.some(item=>item.id===policyForm.provider_id))policyForm.provider_id=preferred
  if(!restoreForm.connection_id)restoreForm.connection_id=connections.value.find(item=>item.status==='active')?.id||''
  if(!selectedSnapshotId.value&&backups.value.length)selectedSnapshotId.value=backups.value[0].id
  if(!copyTargetProviderId.value&&usableCopyTargets.value.length)copyTargetProviderId.value=usableCopyTargets.value[0].id
}

async function load():Promise<void>{
  loading.value=true;storageLoadError.value='';repositoryLoadError.value=''
  const [repoResult,connectionResult,policyResult,backupResult,hubResult]=await Promise.allSettled([
    loadRepositories(),api.get<GitHubConnection[]>('/github/connections'),api.get<BackupPolicy[]>('/platform/backup-policies'),api.get<BackupSnapshot[]>('/platform/backups?limit=200'),api.get<StorageHubOverview>('/storage-hub/overview')
  ])
  if(repoResult.status==='fulfilled')repositories.value=repoResult.value
  else{repositories.value=[];repositoryLoadError.value=message(repoResult.reason)}
  if(connectionResult.status==='fulfilled')connections.value=connectionResult.value
  if(policyResult.status==='fulfilled')policies.value=policyResult.value
  if(backupResult.status==='fulfilled')backups.value=backupResult.value
  if(hubResult.status==='fulfilled')overview.value=hubResult.value
  else{overview.value=null;storageLoadError.value=message(hubResult.reason)}

  try{providers.value=await api.get<StorageProvider[]>('/platform/storage-providers')}
  catch(error){providers.value=[];if(!storageLoadError.value)storageLoadError.value=message(error)}
  assignDefaults();loading.value=false
  if(repositoryLoadError.value)toasts.error('Falha ao listar repositórios',repositoryLoadError.value)
  if(storageLoadError.value)toasts.error('Storage interno indisponível',storageLoadError.value)
}

async function run(key:string,action:()=>Promise<void>):Promise<void>{busy.value=key;try{await action()}catch(error){toasts.error('Operação recusada',message(error))}finally{busy.value=''}}
async function refreshStorage():Promise<void>{await run('storage-refresh',async()=>{overview.value=await api.get<StorageHubOverview>('/storage-hub/overview');providers.value=await api.get<StorageProvider[]>('/platform/storage-providers');storageLoadError.value='';assignDefaults()})}

async function createBucket():Promise<void>{await run('bucket-create',async()=>{const created=await api.post<HubProvider>('/storage-hub/internal-buckets',{name:bucketName.value});toasts.success('Bucket criado',`${created.bucket} está pronto para backup.`);bucketName.value='projetos';await refreshStorage()})}
async function deleteBucket(provider:HubProvider):Promise<void>{if(provider.system_default)return;if(!confirm(`Excluir o bucket ${provider.bucket}? A operação só será aceita se estiver vazio e sem snapshots/políticas.`))return;await run(`bucket-delete-${provider.id}`,async()=>{await api.delete(`/storage-hub/internal-buckets/${provider.id}`);toasts.success('Bucket excluído');await refreshStorage()})}
async function testInternal(provider:HubProvider):Promise<void>{await run(`bucket-test-${provider.id}`,async()=>{const result=await api.post<{ok:boolean;bucket:string}>(`/storage-hub/internal-buckets/${provider.id}/test`,{});toasts.success('Bucket operacional',result.bucket)})}

async function backupNow():Promise<void>{await run('backup-now',async()=>{const result=await api.post<{job_id:string;provider:{name:string}}>('/storage-hub/backups/run',{repository_id:manualForm.repository_id,provider_id:manualForm.provider_id||null,backup_type:manualForm.backup_type,branches:manualForm.branches.split(',').map(v=>v.trim()).filter(Boolean),permanent:manualForm.permanent});toasts.success('Backup iniciado',`${result.provider.name} · Job ${result.job_id}`)})}
async function copySnapshot(snapshot:BackupSnapshot):Promise<void>{if(!copyTargetProviderId.value)return;await run(`copy-${snapshot.id}`,async()=>{const result=await api.post<{job_id:string}>(`/storage-hub/backups/${snapshot.id}/copy`,{provider_id:copyTargetProviderId.value});toasts.success('Cópia agendada',`Job ${result.job_id}. SHA-256 será verificado antes do envio.`)})}

function providerPayload():{config:Record<string,unknown>;secret:Record<string,unknown>}{
  if(providerForm.kind==='s3'||providerForm.kind==='minio')return{config:{endpoint_url:providerForm.endpoint_url||undefined,bucket:providerForm.bucket,region:providerForm.region,prefix:providerForm.prefix},secret:{access_key:providerForm.access_key,secret_key:providerForm.secret_key}}
  if(providerForm.kind==='dropbox')return{config:{base_path:providerForm.base_path,client_id:providerForm.client_id||undefined},secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}}
  if(providerForm.kind==='google_drive')return{config:{folder_id:providerForm.folder_id||undefined,client_id:providerForm.client_id||undefined},secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}}
  return{config:{host:providerForm.host,port:providerForm.port,username:providerForm.username,base_path:providerForm.remote_path,known_hosts:providerForm.known_hosts},secret:{private_key:providerForm.private_key}}
}
function resetProviderForm():void{Object.assign(providerForm,{name:'',kind:'dropbox',endpoint_url:'',bucket:'argws-git-monitor',region:'us-east-1',prefix:'backups',base_path:'/ARGWS Git Monitor',folder_id:'',host:'',port:22,username:'',remote_path:'',access_key:'',secret_key:'',access_token:'',refresh_token:'',client_id:'',client_secret:'',private_key:'',known_hosts:''})}
async function createProvider():Promise<void>{await run('provider-create',async()=>{const payload=providerPayload();const created=await api.post<StorageProvider>('/platform/storage-providers',{name:providerForm.name.trim()||providerLabel(providerForm.kind),kind:providerForm.kind,config:payload.config,secret:payload.secret,enabled:true});toasts.success('Integração salva',`${created.name} cadastrada. Teste antes de usar.`);resetProviderForm();providerFormOpen.value=false;await refreshStorage()})}
async function testProvider(provider:HubProvider):Promise<void>{await run(`provider-test-${provider.id}`,async()=>{const result=await api.post<{ok:boolean;message:string}>(`/platform/storage-providers/${provider.id}/test`,{});result.ok?toasts.success('Integração operacional',result.message):toasts.error('Integração indisponível',result.message)})}
async function deleteProvider(provider:HubProvider):Promise<void>{if(provider.managed)return;if(!confirm(`Excluir ${provider.name}?`))return;await run(`provider-delete-${provider.id}`,async()=>{await api.delete(`/platform/storage-providers/${provider.id}`);toasts.success('Integração removida');await refreshStorage()})}

async function createPolicy():Promise<void>{await run('policy-create',async()=>{await api.post('/platform/backup-policies',{repository_id:policyForm.repository_id,provider_id:policyForm.provider_id,name:policyForm.name,backup_type:policyForm.backup_type,branches:policyForm.branches.split(',').map(v=>v.trim()).filter(Boolean),include_releases:policyForm.include_releases,include_release_assets:policyForm.include_release_assets,include_lfs:policyForm.include_lfs,include_submodules:policyForm.include_submodules,schedule_kind:policyForm.schedule_kind,schedule_value:policyForm.schedule_value||null,event_trigger:policyForm.event_trigger||null,retention:{keep_last:policyForm.keep_last,keep_days:policyForm.keep_days},enabled:true});toasts.success('Política criada');await load()})}
async function runPolicy(policy:BackupPolicy):Promise<void>{await run(`policy-${policy.id}`,async()=>{const result=await api.post<{job_id:string}>(`/platform/backup-policies/${policy.id}/run`,{});toasts.success('Backup enfileirado',`Job ${result.job_id}`)})}
async function retention(policy:BackupPolicy):Promise<void>{await run(`retention-${policy.id}`,async()=>{const result=await api.post<{deleted:number}>(`/platform/backup-policies/${policy.id}/apply-retention`,{});toasts.success('Retenção aplicada',`${result.deleted} snapshot(s) removido(s).`);await load()})}

async function previewRestore(snapshot:BackupSnapshot):Promise<void>{selectedSnapshotId.value=snapshot.id;tab.value='restore';await run('restore-preview',async()=>{restorePreview.value=await api.get<Record<string,unknown>>(`/platform/backups/${snapshot.id}/restore-preview`);restoreForm.confirmation=`RESTAURAR ${snapshot.id}`})}
async function restore(simulate:boolean):Promise<void>{if(!selectedBackup.value)return;await run(simulate?'restore-sim':'restore',async()=>{const body={...restoreForm,connection_id:restoreForm.connection_id||null,repository_full_name:restoreForm.repository_full_name||null,new_repository_name:restoreForm.new_repository_name||null,branch:restoreForm.branch||null,target_path:restoreForm.target_path||null,simulate,confirmation:simulate?null:restoreForm.confirmation};const result=await api.post<Record<string,unknown>>(`/platform/backups/${selectedBackup.value!.id}/restore`,body);simulate?(restorePreview.value=result,toasts.success('Simulação concluída')):toasts.success('Restore enfileirado',`Job ${String(result.job_id||'criado')}`)})}

function handleRealtime(event:Event):void{const detail=(event as CustomEvent<RealtimeEvent>).detail;if(!detail||(!detail.type.startsWith('job.')&&!detail.type.startsWith('backup.')))return;window.clearTimeout(realtimeTimer);realtimeTimer=window.setTimeout(()=>void load(),250)}
onMounted(()=>{window.addEventListener(REALTIME_EVENT,handleRealtime);void load()})
onBeforeUnmount(()=>{window.removeEventListener(REALTIME_EVENT,handleRealtime);window.clearTimeout(realtimeTimer)})
</script>

<template>
  <div class="page-stack backup-workspace">
    <section class="hero-panel storage-hero">
      <div class="hero-copy"><span class="eyebrow">BACKUP & RECOVERY</span><h2>Backup local real, buckets internos e réplica externa</h2><p>Repositórios e storage carregam de forma independente. Uma falha no MinIO não esconde seus projetos; o backup só inicia depois de validar destino e worker.</p><div class="button-row"><button class="button primary" @click="tab='backups'"><DatabaseBackup :size="16"/>Novo backup</button><button class="button secondary" @click="tab='storage'"><CloudCog :size="16"/>Gerenciar storage</button><RouterLink class="button ghost" to="/backup-complete"><Archive :size="16"/>Backup completo + exclusão</RouterLink></div></div>
      <div class="metric-grid"><article class="metric-card"><span>Repositórios</span><strong>{{repositories.length}}</strong><small>disponíveis para backup</small></article><article class="metric-card"><span>Snapshots</span><strong>{{overview?.stats.snapshots||backups.length}}</strong><small>{{overview?.stats.completed||0}} concluído(s)</small></article><article class="metric-card"><span>Armazenado</span><strong>{{size(overview?.stats.stored_bytes)}}</strong><small>snapshots concluídos</small></article><article class="metric-card"><span>MinIO</span><strong class="health-value" :class="minioAvailable?'ok-text':'bad-text'">{{minioAvailable?'ONLINE':'OFFLINE'}}</strong><small>{{overview?.internal_storage.endpoint||'storage interno'}}</small></article></div>
    </section>

    <section v-if="repositoryLoadError" class="alert-callout bad"><TriangleAlert :size="19"/><div><strong>Não foi possível listar repositórios</strong><p>{{repositoryLoadError}}</p></div><button class="button secondary compact" @click="load">Tentar novamente</button></section>
    <section v-if="storageLoadError||overview?.internal_storage.error" class="alert-callout warn"><TriangleAlert :size="19"/><div><strong>Storage interno indisponível, mas os repositórios continuam acessíveis</strong><p>{{storageLoadError||overview?.internal_storage.error}}</p></div><button class="button secondary compact" @click="refreshStorage">Testar novamente</button></section>

    <nav class="segmented-tabs"><button :class="{active:tab==='backups'}" @click="tab='backups'"><DatabaseBackup :size="15"/>Backups</button><button :class="{active:tab==='storage'}" @click="tab='storage'"><Cloud :size="15"/>Storage & Buckets</button><button :class="{active:tab==='policies'}" @click="tab='policies'"><ShieldCheck :size="15"/>Políticas</button><button :class="{active:tab==='restore'}" @click="tab='restore'"><RotateCcw :size="15"/>Restore</button><button class="refresh-tab" :disabled="loading" @click="load"><RefreshCw :size="14" :class="{spin:loading}"/>Atualizar</button></nav>

    <template v-if="tab==='backups'">
      <section class="panel"><header><div><strong>Executar backup agora</strong><span>O repositório vem da base monitorada e o bucket é validado antes da fila.</span></div><DatabaseBackup :size="20"/></header><div class="form-grid three"><label class="field"><span>Repositório</span><select v-model="manualForm.repository_id"><option value="" disabled>{{repositories.length?'Selecione…':'Nenhum repositório carregado'}}</option><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label class="field"><span>Destino</span><select v-model="manualForm.provider_id"><option value="">Bucket principal automático</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}} · {{providerLabel(provider.kind)}}</option></select></label><label class="field"><span>Conteúdo</span><select v-model="manualForm.backup_type"><option value="full">Completo / mirror</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Somente releases</option></select></label></div><label v-if="manualForm.backup_type==='selected_branches'" class="field"><span>Branches/padrões</span><input v-model="manualForm.branches" placeholder="main, develop, release/*"/></label><div class="action-toolbar"><label class="check"><input v-model="manualForm.permanent" type="checkbox"/>Preservar da retenção automática</label><button class="button primary" :disabled="busy==='backup-now'||!manualForm.repository_id" @click="backupNow"><Play :size="15"/>Validar e iniciar</button></div></section>

      <section v-if="usableCopyTargets.length" class="info-callout"><FolderSync :size="19"/><div><strong>Réplica externa disponível</strong><p>Snapshots internos podem ser copiados para Dropbox, Google Drive, S3/MinIO ou SFTP após validação SHA-256.</p></div><label class="field inline-select"><select v-model="copyTargetProviderId"><option v-for="provider in usableCopyTargets" :key="provider.id" :value="provider.id">{{provider.name}}</option></select></label></section>

      <section class="panel table-panel"><header><div><strong>Snapshots</strong><span>Estado real do backup, integridade e destino.</span></div></header><div class="table-wrap"><table><thead><tr><th>Repositório</th><th>Destino</th><th>Status</th><th>Tamanho</th><th>SHA-256</th><th>Data</th><th>Ações</th></tr></thead><tbody><tr v-for="item in backups" :key="item.id"><td><strong>{{repositoryMap[item.repository_id]||item.repository_id}}</strong><small>{{item.backup_type}}</small></td><td>{{providerMap[item.provider_id]||item.provider_id}}</td><td><span class="status-pill" :class="statusClass(item.status)">{{item.status}}</span></td><td>{{size(item.size_bytes)}}</td><td><code>{{item.checksum_sha256?.slice(0,14)||'—'}}</code></td><td>{{when(item.completed_at||item.created_at)}}</td><td><div class="button-row"><button class="button ghost compact" @click="previewRestore(item)"><RotateCcw :size="13"/>Restore</button><button v-if="usableCopyTargets.length&&item.location&&item.status.startsWith('completed')" class="button ghost compact" @click="copySnapshot(item)"><Copy :size="13"/>Copiar</button></div></td></tr><tr v-if="!backups.length&&!loading"><td colspan="7" class="empty">Nenhum snapshot criado ainda.</td></tr></tbody></table></div></section>
    </template>

    <template v-else-if="tab==='storage'">
      <section class="panel"><header><div><strong>MinIO interno · buckets</strong><span>Object storage S3 real, persistente e privado dentro da stack.</span></div><span class="status-pill" :class="minioAvailable?'ok':'bad'">{{minioAvailable?'Online':'Offline'}}</span></header><div class="bucket-create"><label class="field"><span>Novo bucket</span><input v-model="bucketName" maxlength="32" placeholder="projetos" @keyup.enter="createBucket"/></label><button class="button primary" :disabled="busy==='bucket-create'||!bucketName.trim()" @click="createBucket"><FolderPlus :size="15"/>Criar bucket</button></div><div class="bucket-grid"><article v-for="provider in internalBuckets" :key="provider.id" class="storage-card"><div class="storage-card-head"><span class="provider-icon"><Server :size="18"/></span><div><strong>{{provider.bucket_alias||provider.name}}</strong><small>{{provider.bucket}}</small></div><span class="status-dot" :class="provider.available===false?'bad':'ok'"/></div><p>{{provider.system_default?'Bucket principal do sistema':'Bucket criado na aplicação'}}</p><div class="button-row"><button class="button secondary compact" @click="testInternal(provider)"><ShieldCheck :size="13"/>Testar</button><button v-if="!provider.system_default" class="button ghost compact danger-text" @click="deleteBucket(provider)"><Trash2 :size="13"/>Excluir</button></div></article><article v-if="localStorage" class="storage-card"><div class="storage-card-head"><span class="provider-icon"><HardDrive :size="18"/></span><div><strong>Staging local</strong><small>{{localStorage.base_path}}</small></div><span class="status-dot" :class="localStorage.available===false?'bad':'ok'"/></div><p>Área local persistente para recovery e integrações.</p></article></div></section>

      <section class="panel"><header><div><strong>Integrações externas</strong><span>Redundância opcional; o backup interno não depende delas.</span></div><button class="button primary compact" @click="providerFormOpen=!providerFormOpen"><CloudCog :size="14"/>Adicionar</button></header><div v-if="externalProviders.length" class="bucket-grid"><article v-for="provider in externalProviders" :key="provider.id" class="storage-card"><div class="storage-card-head"><span class="provider-icon"><Cloud :size="18"/></span><div><strong>{{provider.name}}</strong><small>{{providerLabel(provider.kind)}} · {{provider.secret_hint||'credencial protegida'}}</small></div></div><div class="button-row"><button class="button secondary compact" @click="testProvider(provider)"><ShieldCheck :size="13"/>Testar</button><button class="button ghost compact danger-text" @click="deleteProvider(provider)"><Trash2 :size="13"/>Excluir</button></div></article></div><p v-else class="empty">Nenhuma integração externa cadastrada.</p></section>

      <section v-if="providerFormOpen" class="panel"><header><div><strong>Nova integração</strong><span>Campos guiados, sem JSON manual.</span></div></header><div class="kind-grid"><button v-for="kind in (['dropbox','google_drive','s3','minio','sftp'] as ProviderKind[])" :key="kind" :class="{active:providerForm.kind===kind}" @click="providerForm.kind=kind">{{providerLabel(kind)}}</button></div><label class="field"><span>Nome amigável</span><input v-model="providerForm.name"/></label><div v-if="providerForm.kind==='s3'||providerForm.kind==='minio'" class="form-grid"><label class="field"><span>Endpoint</span><input v-model="providerForm.endpoint_url"/></label><label class="field"><span>Bucket</span><input v-model="providerForm.bucket"/></label><label class="field"><span>Região</span><input v-model="providerForm.region"/></label><label class="field"><span>Prefixo</span><input v-model="providerForm.prefix"/></label><label class="field"><span>Access Key</span><input v-model="providerForm.access_key"/></label><label class="field"><span>Secret Key</span><input v-model="providerForm.secret_key" type="password"/></label></div><div v-else-if="providerForm.kind==='dropbox'||providerForm.kind==='google_drive'" class="form-grid"><label v-if="providerForm.kind==='dropbox'" class="field"><span>Pasta base</span><input v-model="providerForm.base_path"/></label><label v-else class="field"><span>Folder ID</span><input v-model="providerForm.folder_id"/></label><label class="field"><span>Access Token opcional</span><input v-model="providerForm.access_token" type="password"/></label><label class="field"><span>Refresh Token</span><input v-model="providerForm.refresh_token" type="password"/></label><label class="field"><span>Client ID</span><input v-model="providerForm.client_id"/></label><label class="field"><span>Client Secret</span><input v-model="providerForm.client_secret" type="password"/></label></div><div v-else class="form-grid"><label class="field"><span>Host</span><input v-model="providerForm.host"/></label><label class="field"><span>Porta</span><input v-model.number="providerForm.port" type="number"/></label><label class="field"><span>Usuário</span><input v-model="providerForm.username"/></label><label class="field"><span>Diretório remoto</span><input v-model="providerForm.remote_path"/></label><label class="field"><span>Private key</span><textarea v-model="providerForm.private_key"/></label><label class="field"><span>known_hosts</span><textarea v-model="providerForm.known_hosts"/></label></div><button class="button primary" :disabled="busy==='provider-create'" @click="createProvider">Salvar integração</button></section>
    </template>

    <template v-else-if="tab==='policies'">
      <section class="panel"><header><div><strong>Nova política de backup</strong><span>Agendamento e retenção independentes por repositório.</span></div><ShieldCheck :size="20"/></header><div class="form-grid"><label class="field"><span>Nome</span><input v-model="policyForm.name"/></label><label class="field"><span>Repositório</span><select v-model="policyForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label class="field"><span>Destino</span><select v-model="policyForm.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}}</option></select></label><label class="field"><span>Tipo</span><select v-model="policyForm.backup_type"><option value="full">Completo</option><option value="default_branch">Branch padrão</option><option value="selected_branches">Branches selecionadas</option><option value="all_branches">Todas as branches</option><option value="releases_only">Releases</option></select></label><label class="field"><span>Agendamento</span><select v-model="policyForm.schedule_kind"><option value="manual">Manual</option><option value="interval_hours">A cada X horas</option><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="monthly">Mensal</option><option value="event">Após evento</option></select></label><label class="field"><span>Valor / Evento</span><input v-model="policyForm.schedule_value" placeholder="Ex.: 6"/></label></div><div class="checks"><label><input v-model="policyForm.include_releases" type="checkbox"/> Releases</label><label><input v-model="policyForm.include_release_assets" type="checkbox"/> Assets</label><label><input v-model="policyForm.include_lfs" type="checkbox"/> Git LFS</label><label><input v-model="policyForm.include_submodules" type="checkbox"/> Submodules</label></div><div class="retention-grid"><label class="field"><span>Manter últimos</span><input v-model.number="policyForm.keep_last" type="number" min="0"/></label><label class="field"><span>Manter por dias</span><input v-model.number="policyForm.keep_days" type="number" min="0"/></label></div><button class="button primary" :disabled="!policyForm.repository_id||!policyForm.provider_id" @click="createPolicy">Criar política</button></section><div class="bucket-grid"><article v-for="policy in policies" :key="policy.id" class="storage-card"><strong>{{policy.name}}</strong><small>{{repositoryMap[policy.repository_id]||policy.repository_id}}</small><p>{{policy.schedule_kind}} · {{policy.backup_type}} · último {{when(policy.last_run_at)}}</p><div class="button-row"><button class="button secondary compact" @click="runPolicy(policy)"><Play :size="13"/>Executar</button><button class="button ghost compact" @click="retention(policy)">Aplicar retenção</button></div></article><p v-if="!policies.length" class="empty">Nenhuma política criada.</p></div>
    </template>

    <template v-else>
      <section class="panel"><header><div><strong>Restore controlado</strong><span>Selecione um snapshot, simule e só depois execute.</span></div><RotateCcw :size="20"/></header><label class="field"><span>Snapshot</span><select v-model="selectedSnapshotId"><option v-for="item in backups" :key="item.id" :value="item.id">{{repositoryMap[item.repository_id]||item.repository_id}} · {{when(item.completed_at||item.created_at)}}</option></select></label><div class="form-grid"><label class="field"><span>Destino</span><select v-model="restoreForm.destination"><option value="github_repository">Repositório GitHub existente</option><option value="new_github_repository">Novo repositório GitHub</option><option value="local">Diretório local</option><option value="sftp">SFTP</option></select></label><label class="field"><span>Conexão GitHub</span><select v-model="restoreForm.connection_id"><option value="">—</option><option v-for="connection in connections" :key="connection.id" :value="connection.id">{{connection.name}}</option></select></label><label class="field"><span>Repositório destino</span><input v-model="restoreForm.repository_full_name" placeholder="owner/repo"/></label><label class="field"><span>Novo nome</span><input v-model="restoreForm.new_repository_name"/></label><label class="field"><span>Branch</span><input v-model="restoreForm.branch"/></label><label class="field"><span>Diretório local/SFTP</span><input v-model="restoreForm.target_path"/></label></div><div class="checks"><label><input v-model="restoreForm.restore_tags" type="checkbox"/> Tags</label><label><input v-model="restoreForm.restore_releases" type="checkbox"/> Releases</label></div><div class="button-row"><button class="button secondary" :disabled="!selectedBackup" @click="selectedBackup&&previewRestore(selectedBackup)">Gerar preview</button><button class="button ghost" :disabled="!selectedBackup" @click="restore(true)">Simular</button><button class="button primary" :disabled="!selectedBackup" @click="restore(false)">Executar restore</button></div><pre v-if="restorePreview" class="preview">{{JSON.stringify(restorePreview,null,2)}}</pre></section>
    </template>
  </div>
</template>

<style scoped>
.backup-workspace{gap:1rem}.storage-hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(420px,1fr);gap:1rem}.hero-copy{display:grid;align-content:center;gap:.4rem}.hero-copy h2{margin:0;color:var(--text-strong);font-size:clamp(1.35rem,2vw,2rem)}.hero-copy p{max-width:800px;margin:0 0 .5rem;color:var(--text-muted);font-size:.78rem}.health-value{font-size:1rem!important}.ok-text{color:var(--success)!important}.bad-text{color:var(--danger)!important}.panel{padding:1rem}.panel>header{display:flex;align-items:center;justify-content:space-between;gap:.7rem;margin-bottom:.85rem}.panel>header>div{display:grid}.panel>header strong{color:var(--text-strong)}.panel>header span{color:var(--text-muted);font-size:.68rem}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.action-toolbar{display:flex;align-items:center;justify-content:space-between;gap:.8rem;margin-top:.8rem}.checks{display:flex;flex-wrap:wrap;gap:.8rem;margin:.8rem 0;color:var(--text-muted);font-size:.7rem}.retention-grid{display:grid;grid-template-columns:repeat(2,minmax(0,190px));gap:.7rem;margin-bottom:.8rem}.alert-callout,.info-callout{display:flex;align-items:center;gap:.7rem;padding:.75rem .85rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface)}.alert-callout>div,.info-callout>div{display:grid;flex:1}.alert-callout strong,.info-callout strong{color:var(--text-strong);font-size:.75rem}.alert-callout p,.info-callout p{margin:0;color:var(--text-muted);font-size:.66rem}.alert-callout.bad{border-color:color-mix(in srgb,var(--danger) 35%,var(--border));color:var(--danger)}.alert-callout.warn{border-color:color-mix(in srgb,var(--warning) 35%,var(--border));color:var(--warning)}.bucket-create{display:grid;grid-template-columns:minmax(220px,1fr) auto;align-items:end;gap:.7rem;margin-bottom:.9rem}.bucket-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:.75rem}.storage-card{display:grid;gap:.55rem;padding:.8rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised)}.storage-card-head{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.55rem}.storage-card-head>div{display:grid;min-width:0}.storage-card-head strong{color:var(--text-strong);font-size:.76rem}.storage-card-head small{overflow:hidden;color:var(--text-subtle);font-size:.6rem;text-overflow:ellipsis;white-space:nowrap}.storage-card p{margin:0;color:var(--text-muted);font-size:.65rem}.provider-icon{display:grid;place-items:center;width:2.2rem;height:2.2rem;color:var(--primary-strong);border-radius:.65rem;background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.status-dot{width:.55rem;height:.55rem;border-radius:50%;background:var(--success);box-shadow:0 0 8px color-mix(in srgb,var(--success) 55%,transparent)}.status-dot.bad{background:var(--danger)}.kind-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:.5rem;margin-bottom:.8rem}.kind-grid button{padding:.65rem;color:var(--text-muted);border:1px solid var(--border);border-radius:.7rem;background:var(--surface-raised);cursor:pointer}.kind-grid button.active{color:var(--primary-strong);border-color:var(--primary)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:.7rem;text-align:left;border-bottom:1px solid var(--border-soft);font-size:.68rem;white-space:nowrap}th{color:var(--text-muted);font-size:.58rem;text-transform:uppercase}.status-pill{display:inline-flex;align-items:center;gap:.25rem;padding:.18rem .42rem;border-radius:999px;font-size:.58rem;font-weight:800}.status-pill.ok{color:var(--success);background:color-mix(in srgb,var(--success) 9%,transparent)}.status-pill.bad{color:var(--danger);background:color-mix(in srgb,var(--danger) 9%,transparent)}.status-pill.warn{color:var(--warning)}.status-pill.info{color:var(--primary-strong)}.preview{max-height:360px;overflow:auto;margin-top:.8rem;padding:.75rem;border:1px solid var(--border);border-radius:.7rem;background:var(--surface-soft);font-size:.65rem}.empty{grid-column:1/-1;color:var(--text-muted);text-align:center;padding:1rem}.inline-select{min-width:240px}.danger-text{color:var(--danger)!important}
@media(max-width:1100px){.storage-hero{grid-template-columns:1fr}.form-grid.three{grid-template-columns:1fr 1fr}.kind-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:720px){.form-grid,.form-grid.three,.retention-grid,.bucket-create{grid-template-columns:1fr}.action-toolbar,.alert-callout,.info-callout{align-items:stretch;flex-direction:column}.action-toolbar>.button,.alert-callout>.button,.inline-select{width:100%}.kind-grid{grid-template-columns:1fr 1fr}.table-panel{overflow:hidden}.metric-grid{grid-template-columns:1fr 1fr}}
</style>
