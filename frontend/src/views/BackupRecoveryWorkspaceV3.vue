<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Archive, CheckCircle2, Cloud, CloudCog, Copy, DatabaseBackup, Download, FolderPlus,
  HardDrive, Play, RefreshCw, RotateCcw, Server, ShieldCheck, Trash2,
  TriangleAlert, Wrench, X
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import { useDialogStore } from '../stores/dialog'
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
  secret_hint:string|null; available:boolean|null; has_objects:boolean|null; engine:string|null;
  degraded:boolean; minio_available:boolean|null; fallback_available:boolean|null; storage_error:string|null
}
interface StorageHubOverview {
  providers:HubProvider[]
  stats:{snapshots:number;completed:number;failed:number;stored_bytes:number;last_status:string|null;last_at:string|null;repositories:number}
  internal_storage:{
    object_store:string;engine:string;available:boolean;degraded:boolean;minio_available:boolean;
    fallback_available:boolean;error:string|null;endpoint:string|null;fallback_path:string|null;
    local_staging:string;deployment_manifest_required:boolean
  }
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
interface WorkerDiagnostic { online:boolean; workers:string[]; worker_count:number; error:string|null }
interface MinioDiagnostic {
  ok:boolean; endpoint:string; host:string; port:number; message:string;
  dns:{ok:boolean;addresses:string[];error?:Record<string,unknown>};
  tcp:{ok:boolean;error?:Record<string,unknown>};
  health:{ok:boolean;status:number|null;url?:string;error?:Record<string,unknown>};
  s3:{ok:boolean;authenticated:boolean;bucket_count:number|null;error?:Record<string,unknown>};
  fallback:{ok:boolean;path:string;error?:Record<string,unknown>};
  worker:WorkerDiagnostic
}
interface BackupPreflight {
  ok:boolean; repository:{id:string;full_name:string}; provider:HubProvider;
  storage:Record<string,unknown>; worker:WorkerDiagnostic
}
interface BackupLaunch {
  job_id:string; task_id:string; status:string; provider:HubProvider;
  repository:{id:string;full_name:string}; worker:WorkerDiagnostic
}

const dialogs = useDialogStore()
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
const minioDiagnostic = ref<MinioDiagnostic|null>(null)
const lastLaunch = ref<BackupLaunch|null>(null)
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
const usableCopyTargets = computed(()=>externalProviders.value.filter(item=>item.enabled&&item.available!==false))
const backupTargets = computed(()=>hubProviders.value.filter(item=>item.enabled&&item.available!==false))
const storageState = computed(()=>overview.value?.internal_storage||null)
const storageOperational = computed(()=>storageState.value?.available===true)
const usingFallback = computed(()=>storageState.value?.engine==='local_fallback')
const selectedRepositoryName = computed(()=>repositoryMap.value[manualForm.repository_id]||'Nenhum repositório')
const selectedProviderName = computed(()=>hubProviders.value.find(item=>item.id===manualForm.provider_id)?.name||providerMap.value[manualForm.provider_id]||'Automático · padrão interno')

function message(error:unknown):string{return error instanceof ApiError?error.message:String(error)}
function size(value:number|null|undefined):string{if(!value)return'0 B';const units=['B','KB','MB','GB','TB'];let n=value,i=0;while(n>=1024&&i<units.length-1){n/=1024;i+=1}return`${n.toFixed(i?1:0)} ${units[i]}`}
function when(value:string|null|undefined):string{return value?new Date(value).toLocaleString('pt-BR'):'—'}
function providerLabel(kind:string):string{return({s3:'Amazon S3',minio:'S3 / MinIO',dropbox:'Dropbox',google_drive:'Google Drive',sftp:'SFTP',local:'Local'} as Record<string,string>)[kind]||kind}
function statusClass(value:string):string{if(['completed','success'].includes(value))return'ok';if(value.includes('warning'))return'warn';if(['failed','cancelled'].includes(value))return'bad';return'info'}
function engineLabel(value:string|null|undefined):string{if(value==='minio')return'MinIO / S3';if(value==='local_fallback')return'Local de contingência';if(value==='local')return'Local';return'Indisponível'}
function boolLabel(value:boolean|undefined):string{return value?'OK':'FALHOU'}
function snapshotDownloadable(snapshot:BackupSnapshot):boolean{return Boolean(snapshot.location&&['completed','completed_with_warnings'].includes(snapshot.status))}

function backupPayload(){return{repository_id:manualForm.repository_id,provider_id:manualForm.provider_id||null,backup_type:manualForm.backup_type,branches:manualForm.branches.split(',').map(v=>v.trim()).filter(Boolean),permanent:manualForm.permanent}}
function saveDownload(blob:Blob,filename:string):void{const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;document.body.appendChild(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(url)}

async function loadRepositories():Promise<Repository[]>{const items:Repository[]=[];let page=1,pages=1;do{const response=await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100&monitoring_enabled=true`);items.push(...response.items);pages=response.pages;page+=1}while(page<=pages);return items}

function assignDefaults():void{
  const firstRepo=repositories.value[0]?.id||''
  const preferred=backupTargets.value.find(item=>item.system_default)?.id||backupTargets.value[0]?.id||''
  if(!manualForm.repository_id||!repositories.value.some(item=>item.id===manualForm.repository_id))manualForm.repository_id=firstRepo
  if(manualForm.provider_id&&!backupTargets.value.some(item=>item.id===manualForm.provider_id))manualForm.provider_id=''
  if(!manualForm.provider_id&&preferred)manualForm.provider_id=preferred
  if(!policyForm.repository_id||!repositories.value.some(item=>item.id===policyForm.repository_id))policyForm.repository_id=firstRepo
  if(!policyForm.provider_id||!backupTargets.value.some(item=>item.id===policyForm.provider_id))policyForm.provider_id=preferred
  if(!restoreForm.connection_id)restoreForm.connection_id=connections.value.find(item=>item.status==='active')?.id||''
  if(!selectedSnapshotId.value&&backups.value.length)selectedSnapshotId.value=backups.value[0].id
  if(!copyTargetProviderId.value&&usableCopyTargets.value.length)copyTargetProviderId.value=usableCopyTargets.value[0].id
}

async function load():Promise<void>{
  loading.value=true;storageLoadError.value='';repositoryLoadError.value=''
  const [repoResult,connectionResult,policyResult,backupResult,hubResult,providerResult]=await Promise.allSettled([
    loadRepositories(),api.get<GitHubConnection[]>('/github/connections'),api.get<BackupPolicy[]>('/platform/backup-policies'),api.get<BackupSnapshot[]>('/platform/backups?limit=200'),api.get<StorageHubOverview>('/storage-hub/overview'),api.get<StorageProvider[]>('/platform/storage-providers')
  ])
  if(repoResult.status==='fulfilled')repositories.value=repoResult.value
  else{repositories.value=[];repositoryLoadError.value=message(repoResult.reason)}
  if(connectionResult.status==='fulfilled')connections.value=connectionResult.value
  if(policyResult.status==='fulfilled')policies.value=policyResult.value
  if(backupResult.status==='fulfilled')backups.value=backupResult.value
  if(hubResult.status==='fulfilled')overview.value=hubResult.value
  else{overview.value=null;storageLoadError.value=message(hubResult.reason)}
  if(providerResult.status==='fulfilled')providers.value=providerResult.value
  else{providers.value=[];if(!storageLoadError.value)storageLoadError.value=message(providerResult.reason)}
  assignDefaults();loading.value=false
  if(repositoryLoadError.value)toasts.error('Falha ao listar repositórios',repositoryLoadError.value)
  if(storageLoadError.value)toasts.error('Storage interno indisponível',storageLoadError.value)
}

async function run(key:string,action:()=>Promise<void>):Promise<void>{busy.value=key;try{await action()}catch(error){toasts.error('Operação recusada',message(error))}finally{busy.value=''}}
async function refreshStorage():Promise<void>{await run('storage-refresh',async()=>{overview.value=await api.get<StorageHubOverview>('/storage-hub/overview');providers.value=await api.get<StorageProvider[]>('/platform/storage-providers');storageLoadError.value='';assignDefaults()})}

async function testMinio():Promise<void>{
  await run('minio-test',async()=>{
    const result=await api.post<MinioDiagnostic>('/storage-hub/internal-storage/test',{})
    minioDiagnostic.value=result
    const details=[
      `Endpoint: ${result.endpoint}`,
      `DNS (${result.host}): ${boolLabel(result.dns.ok)}${result.dns.addresses.length?` · ${result.dns.addresses.join(', ')}`:''}`,
      `TCP ${result.host}:${result.port}: ${boolLabel(result.tcp.ok)}`,
      `Health HTTP: ${boolLabel(result.health.ok)}${result.health.status?` · HTTP ${result.health.status}`:''}`,
      `S3 autenticado: ${boolLabel(result.s3.ok)}${result.s3.bucket_count!==null?` · ${result.s3.bucket_count} bucket(s)`:''}`,
      `Fallback local: ${boolLabel(result.fallback.ok)} · ${result.fallback.path}`,
      `Worker: ${result.worker.online?'ONLINE':'OFFLINE'} · ${result.worker.worker_count} processo(s)`,
    ].join('\n')
    await dialogs.showMessage({title:result.ok?'MinIO / S3 operacional':'Diagnóstico MinIO / S3',message:result.message,details,tone:result.ok?'success':'warning',confirmLabel:'Fechar'})
    await refreshStorage()
  })
}

async function createBucket():Promise<void>{if(!bucketName.value.trim())return;await run('bucket-create',async()=>{const created=await api.post<HubProvider>('/storage-hub/internal-buckets',{name:bucketName.value});toasts.success('Bucket criado',`${created.bucket} está pronto em ${engineLabel(created.engine)}.`);bucketName.value='projetos';await refreshStorage()})}
async function deleteBucket(provider:HubProvider):Promise<void>{if(provider.system_default)return;const confirmed=await dialogs.askConfirmation({title:'Excluir bucket interno?',message:`${provider.bucket_alias||provider.bucket} será removido. A operação só é liberada se não houver objetos, snapshots ou políticas vinculadas.`,tone:'danger',confirmLabel:'Excluir bucket'});if(!confirmed)return;await run(`bucket-delete-${provider.id}`,async()=>{await api.delete(`/storage-hub/internal-buckets/${provider.id}`);toasts.success('Bucket excluído',provider.bucket_alias||provider.bucket||provider.name);await refreshStorage()})}
async function testInternal(provider:HubProvider):Promise<void>{await run(`bucket-test-${provider.id}`,async()=>{const result=await api.post<{ok:boolean;bucket:string;engine:string;degraded:boolean}>(`/storage-hub/internal-buckets/${provider.id}/test`,{});toasts.success('Bucket operacional',`${result.bucket} · ${engineLabel(result.engine)}${result.degraded?' (contingência)':''}`);await refreshStorage()})}

async function backupNow():Promise<void>{
  if(!manualForm.repository_id){await dialogs.showMessage({title:'Selecione um repositório',message:'Escolha o projeto que será protegido antes de iniciar o backup.',tone:'warning'});return}
  await run('backup-now',async()=>{
    const preflight=await api.post<BackupPreflight>('/storage-hub/backups/preflight',backupPayload())
    const engine=engineLabel(String(preflight.storage.engine||preflight.provider.engine||preflight.provider.kind))
    const confirmed=await dialogs.askConfirmation({
      title:'Backup validado · iniciar agora?',
      message:`Repositório: ${preflight.repository.full_name}\nDestino: ${preflight.provider.name}\nStorage: ${engine}\nWorker: ${preflight.worker.worker_count} online`,
      details:'O preflight já testou repositório, destino de gravação e worker. Ao confirmar, o job será publicado na fila e aparecerá abaixo.',
      tone:preflight.provider.degraded?'warning':'info',
      confirmLabel:'Iniciar backup',
    })
    if(!confirmed)return
    const launched=await api.post<BackupLaunch>('/storage-hub/backups/run',backupPayload())
    lastLaunch.value=launched
    toasts.success('Backup enviado ao worker',`${launched.repository.full_name} · Job ${launched.job_id}`)
    window.setTimeout(()=>void load(),1200)
  })
}
async function downloadSnapshot(snapshot:BackupSnapshot):Promise<void>{if(!snapshotDownloadable(snapshot))return;await run(`download-${snapshot.id}`,async()=>{const result=await api.download(`/storage-hub/backups/${snapshot.id}/download`);const repo=(repositoryMap.value[snapshot.repository_id]||'argws-backup').replace(/[^A-Za-z0-9._-]+/g,'-');const filename=result.filename||`${repo}-${snapshot.id}.tar.gz`;saveDownload(result.blob,filename);toasts.success('Backup baixado',`${repositoryMap.value[snapshot.repository_id]||snapshot.id} · ${size(snapshot.size_bytes)}`)})}
async function copySnapshot(snapshot:BackupSnapshot):Promise<void>{if(!copyTargetProviderId.value)return;await run(`copy-${snapshot.id}`,async()=>{const result=await api.post<{job_id:string}>(`/storage-hub/backups/${snapshot.id}/copy`,{provider_id:copyTargetProviderId.value});toasts.success('Cópia agendada',`Job ${result.job_id}. SHA-256 será verificado antes do envio.`)})}

function providerPayload():{config:Record<string,unknown>;secret:Record<string,unknown>}{if(providerForm.kind==='s3'||providerForm.kind==='minio')return{config:{endpoint_url:providerForm.endpoint_url||undefined,bucket:providerForm.bucket,region:providerForm.region,prefix:providerForm.prefix},secret:{access_key:providerForm.access_key,secret_key:providerForm.secret_key}};if(providerForm.kind==='dropbox')return{config:{base_path:providerForm.base_path,client_id:providerForm.client_id||undefined},secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}};if(providerForm.kind==='google_drive')return{config:{folder_id:providerForm.folder_id||undefined,client_id:providerForm.client_id||undefined},secret:{access_token:providerForm.access_token||undefined,refresh_token:providerForm.refresh_token||undefined,client_id:providerForm.client_id||undefined,client_secret:providerForm.client_secret||undefined}};return{config:{host:providerForm.host,port:providerForm.port,username:providerForm.username,base_path:providerForm.remote_path,known_hosts:providerForm.known_hosts},secret:{private_key:providerForm.private_key}}}
function resetProviderForm():void{Object.assign(providerForm,{name:'',kind:'dropbox',endpoint_url:'',bucket:'argws-git-monitor',region:'us-east-1',prefix:'backups',base_path:'/ARGWS Git Monitor',folder_id:'',host:'',port:22,username:'',remote_path:'',access_key:'',secret_key:'',access_token:'',refresh_token:'',client_id:'',client_secret:'',private_key:'',known_hosts:''})}
async function createProvider():Promise<void>{await run('provider-create',async()=>{const payload=providerPayload();const created=await api.post<StorageProvider>('/platform/storage-providers',{name:providerForm.name.trim()||providerLabel(providerForm.kind),kind:providerForm.kind,config:payload.config,secret:payload.secret,enabled:true});toasts.success('Integração salva',`${created.name} cadastrada. Teste antes de usar.`);resetProviderForm();providerFormOpen.value=false;await refreshStorage()})}
async function testProvider(provider:HubProvider):Promise<void>{await run(`provider-test-${provider.id}`,async()=>{const result=await api.post<{ok:boolean;message:string}>(`/platform/storage-providers/${provider.id}/test`,{});result.ok?toasts.success('Integração operacional',result.message):toasts.error('Integração indisponível',result.message)})}
async function deleteProvider(provider:HubProvider):Promise<void>{if(provider.managed)return;const confirmed=await dialogs.askConfirmation({title:'Remover integração externa?',message:`${provider.name} será removida do Git Monitor. Os arquivos já existentes no serviço externo não são apagados automaticamente.`,tone:'warning',confirmLabel:'Remover integração'});if(!confirmed)return;await run(`provider-delete-${provider.id}`,async()=>{await api.delete(`/platform/storage-providers/${provider.id}`);toasts.success('Integração removida');await refreshStorage()})}

async function createPolicy():Promise<void>{if(!policyForm.repository_id){toasts.warning('Selecione um repositório');return}await run('policy-create',async()=>{await api.post('/platform/backup-policies',{repository_id:policyForm.repository_id,provider_id:policyForm.provider_id||null,name:policyForm.name,backup_type:policyForm.backup_type,branches:policyForm.branches.split(',').map(v=>v.trim()).filter(Boolean),include_releases:policyForm.include_releases,include_release_assets:policyForm.include_release_assets,include_lfs:policyForm.include_lfs,include_submodules:policyForm.include_submodules,schedule_kind:policyForm.schedule_kind,schedule_value:policyForm.schedule_value||null,event_trigger:policyForm.event_trigger||null,retention:{keep_last:policyForm.keep_last,keep_days:policyForm.keep_days},enabled:true});toasts.success('Política criada');await load()})}
async function runPolicy(policy:BackupPolicy):Promise<void>{await run(`policy-${policy.id}`,async()=>{const result=await api.post<{job_id:string}>(`/platform/backup-policies/${policy.id}/run`,{});toasts.success('Backup enfileirado',`Job ${result.job_id}`)})}
async function retention(policy:BackupPolicy):Promise<void>{const confirmed=await dialogs.askConfirmation({title:'Aplicar retenção agora?',message:'Snapshots fora das regras de retenção poderão ser excluídos. Snapshots permanentes permanecem protegidos.',tone:'warning',confirmLabel:'Aplicar retenção'});if(!confirmed)return;await run(`retention-${policy.id}`,async()=>{const result=await api.post<{deleted:number}>(`/platform/backup-policies/${policy.id}/apply-retention`,{});toasts.success('Retenção aplicada',`${result.deleted} snapshot(s) removido(s).`);await load()})}

async function previewRestore(snapshot:BackupSnapshot):Promise<void>{selectedSnapshotId.value=snapshot.id;tab.value='restore';await run('restore-preview',async()=>{restorePreview.value=await api.get<Record<string,unknown>>(`/platform/backups/${snapshot.id}/restore-preview`);restoreForm.confirmation=`RESTAURAR ${snapshot.id}`})}
async function restore(simulate:boolean):Promise<void>{if(!selectedBackup.value)return;if(!simulate){const confirmed=await dialogs.askConfirmation({title:'Executar restauração?',message:`O snapshot ${selectedBackup.value.id} será aplicado ao destino configurado. Faça a simulação antes se ainda não conferiu o plano.`,tone:'warning',confirmLabel:'Restaurar agora'});if(!confirmed)return}await run(simulate?'restore-sim':'restore',async()=>{const body={...restoreForm,connection_id:restoreForm.connection_id||null,repository_full_name:restoreForm.repository_full_name||null,new_repository_name:restoreForm.new_repository_name||null,branch:restoreForm.branch||null,target_path:restoreForm.target_path||null,simulate,confirmation:simulate?null:restoreForm.confirmation};const result=await api.post<Record<string,unknown>>(`/platform/backups/${selectedBackup.value!.id}/restore`,body);simulate?(restorePreview.value=result,toasts.success('Simulação concluída')):toasts.success('Restore enfileirado',`Job ${String(result.job_id||'criado')}`)})}

function handleRealtime(event:Event):void{const detail=(event as CustomEvent<RealtimeEvent>).detail;if(!detail||(!detail.type.startsWith('job.')&&!detail.type.startsWith('backup.')))return;window.clearTimeout(realtimeTimer);realtimeTimer=window.setTimeout(()=>void load(),250)}
onMounted(()=>{window.addEventListener(REALTIME_EVENT,handleRealtime);void load()})
onBeforeUnmount(()=>{window.removeEventListener(REALTIME_EVENT,handleRealtime);window.clearTimeout(realtimeTimer)})
</script>

<template>
  <div class="backup-workspace page-stack">
    <section class="backup-hero">
      <div class="hero-copy">
        <span class="eyebrow">BACKUP & RECOVERY</span>
        <h2>Backup operacional, diagnóstico S3 e recuperação verificável</h2>
        <p>O Git Monitor testa o caminho inteiro antes de iniciar: repositório, storage e worker. MinIO/S3 é preferencial; o object store local mantém o backup disponível em contingência.</p>
        <div class="hero-actions"><button class="button primary" @click="tab='backups'"><DatabaseBackup :size="16"/>Novo backup</button><button class="button secondary" @click="tab='storage'"><CloudCog :size="16"/>Gerenciar storage</button><RouterLink class="button secondary" to="/backup-complete"><Archive :size="16"/>Backup completo + exclusão</RouterLink></div>
      </div>
      <div class="hero-metrics">
        <article><span>REPOSITÓRIOS</span><strong>{{overview?.stats.repositories??repositories.length}}</strong><small>disponíveis para backup</small></article>
        <article><span>SNAPSHOTS</span><strong>{{overview?.stats.snapshots??backups.length}}</strong><small>{{overview?.stats.completed??0}} concluído(s)</small></article>
        <article><span>ARMAZENADO</span><strong>{{size(overview?.stats.stored_bytes)}}</strong><small>snapshots concluídos</small></article>
        <article :class="{degraded:usingFallback,bad:!storageOperational}"><span>STORAGE</span><strong>{{storageOperational?(usingFallback?'LOCAL':'S3'):'OFFLINE'}}</strong><small>{{engineLabel(storageState?.engine)}}</small></article>
      </div>
    </section>

    <section v-if="storageOperational&&usingFallback" class="runtime-banner warn"><TriangleAlert :size="18"/><div><strong>MinIO/S3 indisponível · contingência local ativa</strong><p>O backup pode funcionar em {{storageState?.fallback_path||'/data/backups/object-store'}}. Use o diagnóstico para descobrir se a falha é DNS, TCP, healthcheck ou autenticação S3.</p></div><button class="button secondary compact" :disabled="busy==='minio-test'" @click="testMinio"><Wrench :size="14"/>Diagnosticar MinIO/S3</button></section>
    <section v-else-if="!storageOperational" class="runtime-banner bad"><TriangleAlert :size="18"/><div><strong>Storage interno indisponível</strong><p>{{storageState?.error||storageLoadError||'MinIO e armazenamento local não responderam.'}}</p></div><button class="button secondary compact" @click="testMinio"><Wrench :size="14"/>Diagnosticar</button></section>
    <section v-else class="runtime-banner ok"><CheckCircle2 :size="18"/><div><strong>MinIO / S3 interno operacional</strong><p>O endpoint S3 está disponível; o fallback local permanece preparado para contingência.</p></div><button class="button ghost compact" @click="testMinio"><Wrench :size="14"/>Diagnóstico</button></section>

    <nav class="workspace-tabs"><button :class="{active:tab==='backups'}" @click="tab='backups'"><DatabaseBackup :size="15"/>Backups</button><button :class="{active:tab==='storage'}" @click="tab='storage'"><Cloud :size="15"/>Storage & Buckets</button><button :class="{active:tab==='policies'}" @click="tab='policies'"><ShieldCheck :size="15"/>Políticas</button><button :class="{active:tab==='restore'}" @click="tab='restore'"><RotateCcw :size="15"/>Restore</button><button class="refresh-tab" @click="load"><RefreshCw :size="14"/>Atualizar</button></nav>

    <template v-if="tab==='backups'">
      <section v-if="lastLaunch" class="launch-card"><CheckCircle2 :size="18"/><div><strong>Backup enviado ao worker</strong><span>{{lastLaunch.repository.full_name}} · {{lastLaunch.provider.name}}</span><code>Job {{lastLaunch.job_id}} · Task {{lastLaunch.task_id}}</code></div><RouterLink class="button ghost compact" to="/jobs">Abrir Fila</RouterLink></section>
      <section class="workspace-card">
        <header><div><h3>Executar backup agora</h3><p>O botão sempre executa um preflight real no backend. O destino automático funciona mesmo quando a lista visual de providers ainda estiver sendo reconciliada.</p></div><DatabaseBackup :size="20"/></header>
        <div v-if="repositoryLoadError" class="inline-error">{{repositoryLoadError}}</div>
        <div class="backup-form-grid">
          <label><span>Repositório</span><select v-model="manualForm.repository_id"><option value="">Selecione…</option><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label>
          <label><span>Destino</span><select v-model="manualForm.provider_id"><option value="">Automático · padrão interno</option><option v-for="provider in backupTargets" :key="provider.id" :value="provider.id">{{provider.name}} · {{engineLabel(provider.engine)}}</option></select></label>
          <label><span>Conteúdo</span><select v-model="manualForm.backup_type"><option value="full">Completo / mirror</option><option value="default_branch">Branch principal</option><option value="all_branches">Todas as branches</option><option value="selected_branches">Branches selecionadas</option><option value="releases_only">Somente releases</option></select></label>
          <label v-if="manualForm.backup_type==='selected_branches'" class="wide"><span>Branches / padrões</span><input v-model="manualForm.branches" placeholder="main, release/*"/></label>
        </div>
        <div class="form-footer"><label class="check-option"><input v-model="manualForm.permanent" type="checkbox"/><span>Preservar snapshot da retenção automática</span></label><button class="button primary" :disabled="busy==='backup-now'||!repositories.length||!manualForm.repository_id" @click="backupNow"><Play :size="15"/>{{busy==='backup-now'?'Validando…':'Validar e iniciar backup'}}</button></div>
      </section>

      <section class="workspace-card"><header><div><h3>Snapshots</h3><p>Integridade, origem, tamanho, data, download e ações de recuperação.</p></div></header><div v-if="loading" class="empty-panel">Carregando snapshots…</div><div v-else-if="!backups.length" class="empty-panel">Nenhum snapshot criado ainda.</div><div v-else class="snapshot-list"><article v-for="snapshot in backups" :key="snapshot.id" class="snapshot-row"><div><span>REPOSITÓRIO</span><strong>{{repositoryMap[snapshot.repository_id]||snapshot.repository_id}}</strong></div><div><span>DESTINO</span><strong>{{providerMap[snapshot.provider_id]||'Storage interno'}}</strong></div><div><span>STATUS</span><em :class="statusClass(snapshot.status)">{{snapshot.status}}</em></div><div><span>TAMANHO</span><strong>{{size(snapshot.size_bytes)}}</strong></div><div><span>DATA</span><strong>{{when(snapshot.completed_at||snapshot.created_at)}}</strong></div><div class="snapshot-actions"><button v-if="snapshotDownloadable(snapshot)" class="button secondary compact" :disabled="busy===`download-${snapshot.id}`" title="Baixar .tar.gz com SHA-256 validado" @click="downloadSnapshot(snapshot)"><Download :size="13"/>{{busy===`download-${snapshot.id}`?'Baixando…':'Baixar'}}</button><button class="button ghost compact" @click="previewRestore(snapshot)"><RotateCcw :size="13"/>Restore</button><button v-if="usableCopyTargets.length" class="button ghost compact" @click="copySnapshot(snapshot)"><Copy :size="13"/>Replicar</button></div></article></div></section>
    </template>

    <template v-else-if="tab==='storage'">
      <section v-if="minioDiagnostic" class="diagnostic-grid"><article><span>DNS</span><strong :class="minioDiagnostic.dns.ok?'ok':'bad'">{{boolLabel(minioDiagnostic.dns.ok)}}</strong><small>{{minioDiagnostic.dns.addresses.join(', ')||minioDiagnostic.host}}</small></article><article><span>TCP {{minioDiagnostic.port}}</span><strong :class="minioDiagnostic.tcp.ok?'ok':'bad'">{{boolLabel(minioDiagnostic.tcp.ok)}}</strong><small>{{minioDiagnostic.endpoint}}</small></article><article><span>HEALTH HTTP</span><strong :class="minioDiagnostic.health.ok?'ok':'bad'">{{boolLabel(minioDiagnostic.health.ok)}}</strong><small>{{minioDiagnostic.health.status?`HTTP ${minioDiagnostic.health.status}`:'sem resposta'}}</small></article><article><span>S3 AUTH</span><strong :class="minioDiagnostic.s3.ok?'ok':'bad'">{{boolLabel(minioDiagnostic.s3.ok)}}</strong><small>{{minioDiagnostic.s3.bucket_count??0}} bucket(s)</small></article><article><span>WORKER</span><strong :class="minioDiagnostic.worker.online?'ok':'bad'">{{minioDiagnostic.worker.online?'ONLINE':'OFFLINE'}}</strong><small>{{minioDiagnostic.worker.worker_count}} processo(s)</small></article></section>
      <section class="workspace-card">
        <header><div><h3>Buckets internos</h3><p>Namespaces gerenciados pelo Git Monitor. O teste de cada bucket valida o engine efetivamente usado.</p></div><div class="header-actions"><span class="engine-badge" :class="{warn:usingFallback}">{{engineLabel(storageState?.engine)}}</span><button class="button ghost compact" :disabled="busy==='minio-test'" @click="testMinio"><Wrench :size="13"/>Testar MinIO/S3</button></div></header>
        <div class="bucket-create"><input v-model="bucketName" placeholder="novo-bucket" @keyup.enter="createBucket"/><button class="button primary" :disabled="busy==='bucket-create'||!storageOperational" @click="createBucket"><FolderPlus :size="15"/>Criar bucket</button></div>
        <div class="bucket-grid">
          <article v-for="provider in internalBuckets" :key="provider.id" class="storage-card"><div class="storage-icon"><Server :size="19"/></div><div class="storage-copy"><div class="storage-title"><strong>{{provider.bucket_alias||provider.name}}</strong><span :class="provider.available===false?'bad':provider.degraded?'warn':'ok'">{{provider.available===false?'Offline':provider.degraded?'Contingência':'Online'}}</span></div><code>{{provider.bucket}}</code><small>{{provider.system_default?'Bucket principal do sistema':'Bucket adicional'}} · {{engineLabel(provider.engine)}}</small><p v-if="provider.storage_error">{{provider.storage_error}}</p><div class="storage-actions"><button class="button ghost compact" :disabled="busy===`bucket-test-${provider.id}`" @click="testInternal(provider)">Testar</button><button v-if="!provider.system_default" class="button ghost compact storage-delete" :disabled="busy===`bucket-delete-${provider.id}`" @click="deleteBucket(provider)"><Trash2 :size="13"/><span>Excluir bucket</span></button></div></div></article>
          <article v-if="localStorage" class="storage-card"><div class="storage-icon"><HardDrive :size="19"/></div><div class="storage-copy"><div class="storage-title"><strong>Staging local</strong><span :class="localStorage.available===false?'bad':'ok'">{{localStorage.available===false?'Offline':'Online'}}</span></div><code>{{localStorage.base_path}}</code><small>Área persistente de recovery, staging e integrações.</small></div></article>
        </div>
      </section>

      <section class="workspace-card"><header><div><h3>Integrações externas</h3><p>Redundância opcional para Dropbox, Google Drive, S3/MinIO externo ou SFTP.</p></div><button class="button primary compact" @click="providerFormOpen=true"><CloudCog :size="14"/>Adicionar</button></header><div v-if="!externalProviders.length" class="empty-panel">Nenhuma integração externa cadastrada.</div><div v-else class="external-grid"><article v-for="provider in externalProviders" :key="provider.id" class="external-card"><div><strong>{{provider.name}}</strong><span>{{providerLabel(provider.kind)}}</span></div><div class="external-actions"><button class="button ghost compact" @click="testProvider(provider)">Testar</button><button class="button ghost compact storage-delete" @click="deleteProvider(provider)"><Trash2 :size="13"/><span>Remover</span></button></div></article></div></section>

      <div v-if="providerFormOpen" class="provider-backdrop" @click.self="providerFormOpen=false"><section class="provider-dialog"><header><div><span class="eyebrow">INTEGRAÇÃO EXTERNA</span><h3>Novo destino de redundância</h3></div><button class="icon-button" @click="providerFormOpen=false"><X :size="17"/></button></header><div class="provider-form"><label><span>Tipo</span><select v-model="providerForm.kind"><option value="dropbox">Dropbox</option><option value="google_drive">Google Drive</option><option value="s3">Amazon S3</option><option value="minio">MinIO / S3 compatível</option><option value="sftp">SFTP</option></select></label><label><span>Nome</span><input v-model="providerForm.name" placeholder="Meu backup externo"/></label><template v-if="providerForm.kind==='s3'||providerForm.kind==='minio'"><label><span>Endpoint</span><input v-model="providerForm.endpoint_url" placeholder="https://s3..."/></label><label><span>Bucket</span><input v-model="providerForm.bucket"/></label><label><span>Região</span><input v-model="providerForm.region"/></label><label><span>Prefixo</span><input v-model="providerForm.prefix"/></label><label><span>Access key</span><input v-model="providerForm.access_key"/></label><label><span>Secret key</span><input v-model="providerForm.secret_key" type="password"/></label></template><template v-else-if="providerForm.kind==='dropbox'||providerForm.kind==='google_drive'"><label><span>Access token</span><input v-model="providerForm.access_token" type="password"/></label><label><span>Refresh token</span><input v-model="providerForm.refresh_token" type="password"/></label><label><span>Client ID</span><input v-model="providerForm.client_id"/></label><label><span>Client secret</span><input v-model="providerForm.client_secret" type="password"/></label><label v-if="providerForm.kind==='dropbox'"><span>Pasta base</span><input v-model="providerForm.base_path"/></label><label v-else><span>Folder ID</span><input v-model="providerForm.folder_id"/></label></template><template v-else><label><span>Host</span><input v-model="providerForm.host"/></label><label><span>Porta</span><input v-model.number="providerForm.port" type="number"/></label><label><span>Usuário</span><input v-model="providerForm.username"/></label><label><span>Caminho remoto</span><input v-model="providerForm.remote_path"/></label><label class="wide"><span>Chave privada</span><textarea v-model="providerForm.private_key" rows="5"/></label><label class="wide"><span>known_hosts</span><textarea v-model="providerForm.known_hosts" rows="3"/></label></template></div><footer><button class="button secondary" @click="providerFormOpen=false">Cancelar</button><button class="button primary" :disabled="busy==='provider-create'" @click="createProvider">Salvar integração</button></footer></section></div>
    </template>

    <template v-else-if="tab==='policies'">
      <section class="workspace-card"><header><div><h3>Nova política de backup</h3><p>Agendamento e retenção independentes por repositório.</p></div><ShieldCheck :size="20"/></header><div class="policy-grid"><label><span>Nome</span><input v-model="policyForm.name"/></label><label><span>Repositório</span><select v-model="policyForm.repository_id"><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label><span>Destino</span><select v-model="policyForm.provider_id"><option value="">Automático · padrão interno</option><option v-for="provider in backupTargets" :key="provider.id" :value="provider.id">{{provider.name}}</option></select></label><label><span>Tipo</span><select v-model="policyForm.backup_type"><option value="full">Completo</option><option value="default_branch">Branch principal</option><option value="all_branches">Todas as branches</option><option value="selected_branches">Selecionadas</option><option value="releases_only">Releases</option></select></label><label><span>Agendamento</span><select v-model="policyForm.schedule_kind"><option value="daily">Diário</option><option value="weekly">Semanal</option><option value="interval_hours">Intervalo em horas</option><option value="event">Evento</option></select></label><label><span>Valor / Evento</span><input v-model="policyForm.schedule_value" placeholder="Ex.: 6 para intervalo"/></label></div><div class="check-row"><label><input v-model="policyForm.include_releases" type="checkbox"/>Releases</label><label><input v-model="policyForm.include_release_assets" type="checkbox"/>Assets</label><label><input v-model="policyForm.include_lfs" type="checkbox"/>Git LFS</label><label><input v-model="policyForm.include_submodules" type="checkbox"/>Submodules</label></div><div class="retention-row"><label><span>Manter últimos</span><input v-model.number="policyForm.keep_last" type="number" min="1"/></label><label><span>Manter por dias</span><input v-model.number="policyForm.keep_days" type="number" min="1"/></label><button class="button primary" @click="createPolicy">Criar política</button></div></section>
      <section class="workspace-card"><div v-if="!policies.length" class="empty-panel">Nenhuma política criada.</div><div v-else class="policy-list"><article v-for="policy in policies" :key="policy.id"><div><strong>{{policy.name}}</strong><span>{{repositoryMap[policy.repository_id]||policy.repository_id}} · {{providerMap[policy.provider_id]||policy.provider_id}}</span><small>Último: {{when(policy.last_run_at)}} · Próximo: {{when(policy.next_run_at)}}</small></div><div><button class="button ghost compact" @click="runPolicy(policy)"><Play :size="13"/>Executar</button><button class="button ghost compact" @click="retention(policy)">Retenção</button></div></article></div></section>
    </template>

    <template v-else>
      <section class="workspace-card"><header><div><h3>Restaurar snapshot</h3><p>Simule primeiro, valide o plano e só depois execute a restauração.</p></div><RotateCcw :size="20"/></header><div class="restore-grid"><label><span>Snapshot</span><select v-model="selectedSnapshotId"><option v-for="snapshot in backups" :key="snapshot.id" :value="snapshot.id">{{repositoryMap[snapshot.repository_id]||snapshot.repository_id}} · {{when(snapshot.completed_at||snapshot.created_at)}}</option></select></label><label><span>Destino</span><select v-model="restoreForm.destination"><option value="github_repository">Repositório GitHub</option><option value="local">Diretório local</option></select></label><template v-if="restoreForm.destination==='github_repository'"><label><span>Conexão</span><select v-model="restoreForm.connection_id"><option v-for="connection in connections" :key="connection.id" :value="connection.id">@{{connection.github_login}}</option></select></label><label><span>Repositório existente</span><input v-model="restoreForm.repository_full_name" placeholder="owner/repo"/></label><label><span>Novo nome</span><input v-model="restoreForm.new_repository_name" placeholder="opcional"/></label><label><span>Branch</span><input v-model="restoreForm.branch" placeholder="opcional"/></label></template><label v-else><span>Caminho local</span><input v-model="restoreForm.target_path" placeholder="/restore/projeto"/></label></div><div class="check-row"><label><input v-model="restoreForm.restore_tags" type="checkbox"/>Restaurar tags</label><label><input v-model="restoreForm.restore_releases" type="checkbox"/>Restaurar releases compatíveis</label></div><div class="restore-actions"><button class="button secondary" :disabled="!selectedBackup" @click="restore(true)">Simular</button><button class="button primary" :disabled="!selectedBackup" @click="restore(false)">Restaurar</button></div><pre v-if="restorePreview" class="restore-preview">{{JSON.stringify(restorePreview,null,2)}}</pre></section>
    </template>
  </div>
</template>

<style scoped>
.backup-workspace{gap:1rem}.backup-hero{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(420px,1fr);gap:1rem;padding:1.35rem;border:1px solid color-mix(in srgb,var(--primary) 24%,var(--border));border-radius:1.25rem;background:linear-gradient(110deg,color-mix(in srgb,var(--primary) 7%,var(--surface)),var(--surface) 48%,color-mix(in srgb,#8b5cf6 6%,var(--surface)));box-shadow:var(--shadow-md)}.hero-copy h2{max-width:780px;margin:.2rem 0 .55rem;color:var(--text-strong);font-size:1.55rem;line-height:1.15;letter-spacing:-.035em}.hero-copy p{max-width:820px;margin:0;color:var(--text-muted);font-size:.78rem;line-height:1.6}.hero-actions{display:flex;gap:.55rem;flex-wrap:wrap;margin-top:.9rem}.hero-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:.55rem}.hero-metrics article{display:grid;align-content:start;gap:.45rem;min-width:0;padding:.85rem;border:1px solid var(--border);border-radius:.9rem;background:color-mix(in srgb,var(--surface-raised) 78%,transparent)}.hero-metrics span{color:var(--text-muted);font-size:.55rem;font-weight:850;letter-spacing:.07em}.hero-metrics strong{overflow:hidden;color:var(--text-strong);font-size:1.25rem;text-overflow:ellipsis}.hero-metrics small{color:var(--text-subtle);font-size:.55rem;line-height:1.35}.hero-metrics article.degraded strong{color:var(--warning)}.hero-metrics article.bad strong{color:var(--danger)}
.runtime-banner,.launch-card{display:flex;align-items:center;gap:.75rem;padding:.7rem .85rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface)}.runtime-banner>div,.launch-card>div{flex:1}.runtime-banner strong,.launch-card strong{display:block;color:var(--text-strong);font-size:.73rem}.runtime-banner p{margin:.15rem 0 0;color:var(--text-muted);font-size:.64rem;line-height:1.45}.runtime-banner.warn{border-color:color-mix(in srgb,var(--warning) 38%,var(--border));color:var(--warning)}.runtime-banner.bad{border-color:color-mix(in srgb,var(--danger) 38%,var(--border));color:var(--danger)}.runtime-banner.ok,.launch-card{border-color:color-mix(in srgb,var(--success) 30%,var(--border));color:var(--success)}.launch-card span,.launch-card code{display:block;color:var(--text-muted);font-size:.6rem}.launch-card code{margin-top:.15rem}
.workspace-tabs{display:flex;align-items:center;gap:.2rem;padding:.35rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface-raised)}.workspace-tabs button{display:inline-flex;align-items:center;gap:.35rem;min-height:2.25rem;padding:.4rem .65rem;color:var(--text-muted);border:0;border-radius:.62rem;background:transparent;font:750 .64rem inherit;cursor:pointer}.workspace-tabs button.active{color:var(--text-strong);background:var(--surface);box-shadow:var(--shadow-sm)}.workspace-tabs .refresh-tab{margin-left:auto}.workspace-card{padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.workspace-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem;margin-bottom:.9rem}.workspace-card h3{margin:0;color:var(--text-strong);font-size:.85rem}.workspace-card header p{margin:.18rem 0 0;color:var(--text-muted);font-size:.62rem;line-height:1.45}.header-actions{display:flex;align-items:center;gap:.45rem}.inline-error{margin-bottom:.7rem;padding:.6rem;color:var(--danger);border:1px solid color-mix(in srgb,var(--danger) 25%,var(--border));border-radius:.65rem;background:color-mix(in srgb,var(--danger) 5%,var(--surface));font-size:.68rem}.backup-form-grid,.policy-grid,.restore-grid,.provider-form{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem}.backup-form-grid label,.policy-grid label,.restore-grid label,.provider-form label,.retention-row label{display:grid;gap:.35rem}.backup-form-grid span,.policy-grid span,.restore-grid span,.provider-form span,.retention-row span{color:var(--text-strong);font-size:.61rem;font-weight:800}.backup-form-grid input,.backup-form-grid select,.policy-grid input,.policy-grid select,.restore-grid input,.restore-grid select,.provider-form input,.provider-form select,.provider-form textarea,.bucket-create input,.retention-row input{width:100%;min-height:2.55rem;padding:.5rem .68rem;color:var(--text);border:1px solid var(--border);border-radius:.7rem;outline:0;background:var(--surface-raised);font:inherit;font-size:.72rem}.wide{grid-column:1/-1}.form-footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-top:.8rem}.check-option,.check-row label{display:flex;align-items:center;gap:.45rem;color:var(--text-muted);font-size:.65rem}.check-row{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.75rem}.empty-panel{padding:2rem;color:var(--text-muted);text-align:center;font-size:.75rem}.snapshot-list,.policy-list{display:grid;gap:.5rem}.snapshot-row{display:grid;grid-template-columns:1.5fr 1.2fr .7fr .65fr 1fr auto;align-items:center;gap:.7rem;padding:.7rem;border:1px solid var(--border-soft);border-radius:.75rem;background:var(--surface-raised)}.snapshot-row>div{display:grid;gap:.18rem;min-width:0}.snapshot-row span{color:var(--text-subtle);font-size:.5rem;font-weight:850;letter-spacing:.05em}.snapshot-row strong{overflow:hidden;color:var(--text);font-size:.62rem;text-overflow:ellipsis;white-space:nowrap}.snapshot-row em{width:max-content;padding:.2rem .4rem;border-radius:999px;font-size:.54rem;font-style:normal;font-weight:800}.snapshot-row em.ok{color:var(--success);background:color-mix(in srgb,var(--success) 10%,transparent)}.snapshot-row em.warn{color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,transparent)}.snapshot-row em.bad{color:var(--danger);background:color-mix(in srgb,var(--danger) 10%,transparent)}.snapshot-row em.info{color:var(--primary);background:color-mix(in srgb,var(--primary) 10%,transparent)}.snapshot-actions{display:flex!important;grid-auto-flow:column;gap:.35rem}
.diagnostic-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem}.diagnostic-grid article{display:grid;gap:.25rem;padding:.7rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface)}.diagnostic-grid span{color:var(--text-muted);font-size:.54rem;font-weight:850}.diagnostic-grid strong{font-size:.8rem}.diagnostic-grid strong.ok{color:var(--success)}.diagnostic-grid strong.bad{color:var(--danger)}.diagnostic-grid small{overflow:hidden;color:var(--text-subtle);font-size:.53rem;text-overflow:ellipsis;white-space:nowrap}.engine-badge{padding:.25rem .5rem;color:var(--success);border:1px solid color-mix(in srgb,var(--success) 28%,var(--border));border-radius:999px;font-size:.58rem;font-weight:850}.engine-badge.warn{color:var(--warning);border-color:color-mix(in srgb,var(--warning) 30%,var(--border))}.bucket-create{display:grid;grid-template-columns:1fr auto;gap:.55rem;margin-bottom:.75rem}.bucket-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem}.storage-card{display:flex;align-items:flex-start;gap:.7rem;padding:.8rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised)}.storage-icon{display:grid;place-items:center;width:2.35rem;height:2.35rem;border-radius:.7rem;color:var(--primary);background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.storage-copy{display:grid;gap:.35rem;min-width:0;flex:1}.storage-title{display:flex;align-items:center;justify-content:space-between;gap:.5rem}.storage-title strong{color:var(--text-strong);font-size:.72rem}.storage-title span{padding:.15rem .35rem;border-radius:999px;font-size:.52rem;font-weight:850}.storage-title .ok{color:var(--success);background:color-mix(in srgb,var(--success) 9%,transparent)}.storage-title .warn{color:var(--warning);background:color-mix(in srgb,var(--warning) 9%,transparent)}.storage-title .bad{color:var(--danger);background:color-mix(in srgb,var(--danger) 9%,transparent)}.storage-copy code{overflow:hidden;color:var(--text);font-size:.58rem;text-overflow:ellipsis}.storage-copy small,.storage-copy p{margin:0;color:var(--text-muted);font-size:.57rem;line-height:1.4}.storage-actions{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.2rem}.storage-delete{color:var(--danger)!important;border-color:color-mix(in srgb,var(--danger) 30%,var(--border))!important;background:transparent!important}.storage-delete:hover{color:#fff!important;background:var(--danger)!important}.storage-delete span{color:inherit!important}.external-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}.external-card{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.7rem;border:1px solid var(--border-soft);border-radius:.75rem;background:var(--surface-raised)}.external-card>div:first-child{display:grid;gap:.15rem}.external-card strong{color:var(--text-strong);font-size:.7rem}.external-card span{color:var(--text-muted);font-size:.6rem}.external-actions{display:flex;gap:.35rem}.provider-backdrop{position:fixed;inset:0;z-index:8000;display:grid;place-items:center;padding:1rem;background:rgba(2,8,23,.52);backdrop-filter:blur(5px)}.provider-dialog{width:min(760px,100%);max-height:90vh;overflow:auto;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:0 24px 70px rgba(2,8,23,.28)}.provider-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:.8rem}.provider-dialog h3{margin:.12rem 0}.provider-form{grid-template-columns:repeat(2,minmax(0,1fr))}.provider-dialog footer{display:flex;justify-content:flex-end;gap:.5rem;margin-top:.8rem}.retention-row{display:grid;grid-template-columns:185px 185px auto;align-items:end;gap:.6rem;margin-top:.75rem}.policy-list article{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.75rem;border:1px solid var(--border-soft);border-radius:.75rem;background:var(--surface-raised)}.policy-list article>div:first-child{display:grid;gap:.18rem}.policy-list strong{color:var(--text-strong);font-size:.7rem}.policy-list span,.policy-list small{color:var(--text-muted);font-size:.58rem}.policy-list article>div:last-child{display:flex;gap:.35rem}.restore-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:.75rem}.restore-preview{max-height:360px;margin:.8rem 0 0;padding:.8rem;overflow:auto;color:var(--text-muted);border:1px solid var(--border);border-radius:.75rem;background:var(--surface-raised);font:600 .62rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}
@media(max-width:1200px){.backup-hero{grid-template-columns:1fr}.hero-metrics{grid-template-columns:repeat(4,1fr)}.diagnostic-grid{grid-template-columns:repeat(3,1fr)}.snapshot-row{grid-template-columns:repeat(3,1fr)}.snapshot-actions{grid-column:1/-1}.backup-form-grid,.policy-grid,.restore-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:760px){.hero-metrics,.diagnostic-grid{grid-template-columns:repeat(2,1fr)}.hero-actions,.form-footer,.runtime-banner,.launch-card{align-items:stretch;flex-direction:column}.workspace-tabs{overflow-x:auto}.workspace-tabs button{flex:0 0 auto}.workspace-tabs .refresh-tab{margin-left:0}.backup-form-grid,.policy-grid,.restore-grid,.provider-form,.bucket-grid,.external-grid,.snapshot-row{grid-template-columns:1fr}.wide{grid-column:auto}.bucket-create{grid-template-columns:1fr}.snapshot-actions{grid-column:auto}.retention-row{grid-template-columns:1fr}.policy-list article,.external-card{align-items:stretch;flex-direction:column}.policy-list article>div:last-child,.external-actions{width:100%}.policy-list .button,.external-actions .button{flex:1}.provider-backdrop{align-items:end;padding:.5rem}.provider-dialog{max-height:92vh;border-radius:1rem}.header-actions{align-items:flex-end;flex-direction:column}}
</style>
