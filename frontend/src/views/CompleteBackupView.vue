<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Archive, AlertTriangle, CheckCircle2, DatabaseBackup, Play, RefreshCw, ShieldCheck, Trash2 } from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'
import type { PaginatedResponse, Repository } from '../types/api'

interface StorageProvider { id:string; name:string; kind:string; enabled:boolean; config:Record<string,unknown> }
interface LifecycleResponse { job_id:string; task_id:string; repository:string; provider:string; delete_after_backup:boolean; status:string; safety:string }

const route=useRoute()
const toasts=useToastStore()
const loading=ref(true)
const busy=ref(false)
const repositories=ref<Repository[]>([])
const providers=ref<StorageProvider[]>([])
const lastJob=ref<LifecycleResponse|null>(null)
const form=reactive({repository_id:'',provider_id:'',delete_after_backup:false,confirmation:''})

const selectedRepository=computed(()=>repositories.value.find(item=>item.id===form.repository_id)||null)
const expectedConfirmation=computed(()=>selectedRepository.value ? `BACKUP E EXCLUIR ${selectedRepository.value.full_name}` : '')
const canRun=computed(()=>Boolean(form.repository_id&&form.provider_id&&(!form.delete_after_backup||form.confirmation===expectedConfirmation.value)))

function errorMessage(error:unknown):string{return error instanceof ApiError?error.message:String(error)}

async function loadRepositories():Promise<Repository[]>{
  const items:Repository[]=[];let page=1;let pages=1
  do{const response=await api.get<PaginatedResponse<Repository>>(`/repositories?monitoring_enabled=true&page=${page}&page_size=100`);items.push(...response.items);pages=response.pages;page+=1}while(page<=pages)
  return items
}

async function load():Promise<void>{
  loading.value=true
  try{
    const [repos,storage]=await Promise.all([loadRepositories(),api.get<StorageProvider[]>('/platform/storage-providers')])
    repositories.value=repos
    providers.value=storage.filter(item=>item.enabled)
    const requested=String(route.query.repository||'')
    if(!form.repository_id)form.repository_id=repos.some(item=>item.id===requested)?requested:(repos[0]?.id||'')
    if(!form.provider_id)form.provider_id=providers.value[0]?.id||''
  }catch(error){toasts.error('Falha ao carregar backup completo',errorMessage(error))}
  finally{loading.value=false}
}

function toggleDelete():void{
  form.delete_after_backup=!form.delete_after_backup
  form.confirmation=''
}

async function execute():Promise<void>{
  if(!canRun.value||busy.value)return
  if(form.delete_after_backup&&!confirm(
    `O Git Monitor fará o backup completo, validará os checksums e SOMENTE DEPOIS tentará excluir ${selectedRepository.value?.full_name} do GitHub.\n\nSe houver qualquer warning no backup, a exclusão será bloqueada. Continuar?`
  ))return
  busy.value=true
  try{
    const result=await api.post<LifecycleResponse>(`/backup-lifecycle/${form.repository_id}/complete`,{
      provider_id:form.provider_id,
      delete_after_backup:form.delete_after_backup,
      confirmation:form.delete_after_backup?form.confirmation:null
    })
    lastJob.value=result
    toasts.success(form.delete_after_backup?'Backup + exclusão iniciado':'Backup completo iniciado',`Job ${result.job_id}. Acompanhe o progresso em Fila.`)
    form.confirmation=''
  }catch(error){toasts.error('Operação não iniciada',errorMessage(error))}
  finally{busy.value=false}
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div><span class="eyebrow">ARQUIVAMENTO FORENSE</span><h2>Backup completo do GitHub</h2><p>Preserva Git, refs, releases, assets, LFS, submódulos e um sidecar de metadados com PRs, reviews, issues, comentários, Actions, logs e artifacts disponíveis.</p></div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
    </section>

    <section class="coverage-grid">
      <article class="coverage-card"><DatabaseBackup :size="21"/><div><strong>Snapshot primário</strong><span>Mirror Git + bundle + refs + releases/assets + LFS + submódulos.</span></div></article>
      <article class="coverage-card"><Archive :size="21"/><div><strong>Sidecar GitHub</strong><span>PRs, reviews, issues, comentários, workflows, runs, jobs, settings, logs e artifacts ainda disponíveis.</span></div></article>
      <article class="coverage-card"><ShieldCheck :size="21"/><div><strong>Exclusão fail-closed</strong><span>Dois checksums SHA-256 e zero warnings são obrigatórios antes de excluir remotamente.</span></div></article>
    </section>

    <section class="panel">
      <header><div><strong>Executar backup completo</strong><span>Use um provider Local, S3, MinIO, Dropbox, Google Drive ou SFTP já validado.</span></div></header>
      <div class="form-grid">
        <label class="field"><span>Repositório</span><select v-model="form.repository_id" @change="form.confirmation='' "><option v-for="repo in repositories" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label>
        <label class="field"><span>Destino</span><select v-model="form.provider_id"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{provider.name}} · {{provider.kind}}</option></select></label>
      </div>

      <button type="button" class="danger-mode" :class="{active:form.delete_after_backup}" @click="toggleDelete">
        <span class="mode-icon"><Trash2 :size="18"/></span><span><strong>Backup e excluir do GitHub</strong><small>Opcional. O registro local vira tombstone e permanece vinculado aos snapshots para auditoria e restauração.</small></span>
      </button>

      <div v-if="form.delete_after_backup" class="danger-confirm">
        <AlertTriangle :size="20"/>
        <div><strong>Confirmação destrutiva</strong><p>Digite exatamente <code>{{expectedConfirmation}}</code>. A exclusão só é tentada depois do backup completo sem warnings.</p><input v-model="form.confirmation" :placeholder="expectedConfirmation" autocomplete="off"/></div>
      </div>

      <div class="actions"><button class="button primary" :disabled="busy||!canRun" @click="execute"><Play :size="16"/>{{busy?'Iniciando…':form.delete_after_backup?'Backup completo + excluir':'Iniciar backup completo'}}</button></div>
    </section>

    <section v-if="lastJob" class="panel result-panel">
      <CheckCircle2 :size="22"/><div><strong>Operação aceita</strong><p>{{lastJob.safety}}</p><div class="job-meta"><code>job: {{lastJob.job_id}}</code><code>task: {{lastJob.task_id}}</code></div><div class="result-actions"><RouterLink class="button secondary compact" to="/jobs">Acompanhar na Fila</RouterLink><RouterLink class="button secondary compact" to="/backup-recovery">Ver snapshots</RouterLink></div></div>
    </section>

    <section class="panel limitations">
      <header><div><strong>O que o GitHub não permite restaurar de forma idêntica</strong><span>Esses limites são da plataforma remota, não do arquivo gerado.</span></div></header>
      <ul><li>Valores de secrets não podem ser lidos pela API; somente nomes/metadados são arquivados.</li><li>Runs, logs e artifacts históricos podem ser arquivados, porém não podem ser reinjetados com os mesmos IDs, timestamps e histórico de execução.</li><li>PRs/issues/reviews são preservados no sidecar como registro histórico; o restore funcional principal recompõe Git/refs e releases, sem fingir que a API consegue recriar identidade histórica perfeita.</li></ul>
    </section>
  </div>
</template>

<style scoped>
.coverage-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem}.coverage-card{display:flex;align-items:flex-start;gap:.65rem;padding:.85rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface)}.coverage-card>svg{flex:none;color:var(--primary-strong)}.coverage-card div{display:grid;gap:.2rem}.coverage-card strong{color:var(--text-strong);font-size:.75rem}.coverage-card span{color:var(--text-muted);font-size:.65rem;line-height:1.4}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}.danger-mode{display:flex;align-items:flex-start;gap:.7rem;width:100%;margin-top:1rem;padding:.8rem;text-align:left;border:1px solid var(--border);border-radius:.8rem;background:var(--surface-raised);cursor:pointer}.danger-mode.active{border-color:color-mix(in srgb,var(--danger) 55%,var(--border));background:color-mix(in srgb,var(--danger) 6%,var(--surface))}.mode-icon{display:grid;place-items:center;flex:none;width:2rem;height:2rem;border-radius:.6rem;color:var(--danger);background:color-mix(in srgb,var(--danger) 10%,var(--surface))}.danger-mode span:last-child{display:grid;gap:.2rem}.danger-mode strong{color:var(--text-strong);font-size:.75rem}.danger-mode small{color:var(--text-muted);font-size:.64rem;line-height:1.4}.danger-confirm{display:flex;align-items:flex-start;gap:.7rem;margin-top:.8rem;padding:.8rem;border:1px solid color-mix(in srgb,var(--danger) 35%,var(--border));border-radius:.8rem;background:color-mix(in srgb,var(--danger) 5%,var(--surface))}.danger-confirm>svg{flex:none;color:var(--danger)}.danger-confirm div{width:100%}.danger-confirm strong{color:var(--danger)}.danger-confirm p{margin:.2rem 0 .6rem;color:var(--text-muted);font-size:.68rem}.danger-confirm code{color:var(--text-strong)}.danger-confirm input{width:100%;min-height:2.45rem;padding:.55rem .65rem;border:1px solid var(--border);border-radius:.6rem;background:var(--surface-raised);color:var(--text)}.actions{display:flex;justify-content:flex-end;margin-top:.9rem}.result-panel{display:flex;align-items:flex-start;gap:.7rem;border-color:color-mix(in srgb,var(--success) 35%,var(--border))}.result-panel>svg{flex:none;color:var(--success)}.result-panel strong{color:var(--text-strong)}.result-panel p{margin:.2rem 0 .6rem;color:var(--text-muted);font-size:.68rem}.job-meta,.result-actions{display:flex;gap:.4rem;flex-wrap:wrap}.job-meta code{padding:.2rem .35rem;border-radius:.35rem;background:var(--surface-raised);font-size:.62rem}.result-actions{margin-top:.65rem}.limitations ul{margin:.7rem 0 0;padding-left:1.2rem;color:var(--text-muted);font-size:.68rem;line-height:1.55}.limitations li+li{margin-top:.35rem}
@media(max-width:820px){.coverage-grid{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}.actions .button{width:100%}}
</style>
