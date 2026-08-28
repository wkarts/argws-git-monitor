<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  AlertTriangle, CheckCircle2, CircleDotDashed, ExternalLink, Globe2, LockKeyhole,
  MessageCircle, Plus, RefreshCw, Search, X
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import OperationStatusBanner from '../components/OperationStatusBanner.vue'
import PaginationBar from '../components/PaginationBar.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { MessageResponse, OperationIssue, PaginatedResponse, Repository } from '../types/api'

const dialogs = useDialogStore()
const toasts = useToastStore()
const response = ref<PaginatedResponse<OperationIssue> | null>(null)
const repositories = ref<Repository[]>([])
const loading = ref(true)
const errorMessage = ref('')
const query = ref('')
const page = ref(1)
const showCreate = ref(false)
const busyIssue = ref<string | null>(null)
const createForm = reactive({ repository_id: '', title: '', body: '' })
let debounceTimer:number|undefined

const repoOptions = computed(() => repositories.value.filter((item)=>item.monitoring_enabled).sort((a,b)=>a.full_name.localeCompare(b.full_name)))
function buildQuery():string{const params=new URLSearchParams({page:String(page.value),page_size:'30'});if(query.value.trim())params.set('q',query.value.trim());return params.toString()}
async function loadRepositories():Promise<void>{const all:Repository[]=[];let p=1,pages=1;do{const r=await api.get<PaginatedResponse<Repository>>(`/repositories?page=${p}&page_size=100`);all.push(...r.items);pages=r.pages;p++}while(p<=pages);repositories.value=all;if(!createForm.repository_id&&all[0])createForm.repository_id=all[0].id}
async function load():Promise<void>{loading.value=true;errorMessage.value='';try{response.value=await api.get<PaginatedResponse<OperationIssue>>(`/operations/issues?${buildQuery()}`);if(!repositories.value.length)await loadRepositories()}catch(error){errorMessage.value=error instanceof ApiError?error.message:'Não foi possível carregar as issues.'}finally{loading.value=false}}
function changePage(target:number):void{page.value=target;void load();window.scrollTo({top:0,behavior:'smooth'})}
async function createIssue():Promise<void>{if(!createForm.repository_id||!createForm.title.trim())return;busyIssue.value='create';try{const result=await api.post<MessageResponse>('/operations/issues',{repository_id:createForm.repository_id,title:createForm.title.trim(),body:createForm.body.trim()||null});toasts.success('Issue criada',result.message);Object.assign(createForm,{repository_id:createForm.repository_id,title:'',body:''});showCreate.value=false;await load()}catch(error){toasts.error('Não foi possível criar',error instanceof ApiError?error.message:undefined)}finally{busyIssue.value=null}}
async function closeIssue(issue:OperationIssue):Promise<void>{
  const accepted=await dialogs.askConfirmation({title:'Fechar issue no GitHub?',message:`#${issue.number} · ${issue.title}\n\nA issue será marcada como fechada no repositório ${issue.repository_full_name}.`,tone:'warning',confirmLabel:'Fechar issue'})
  if(!accepted)return
  busyIssue.value=issue.id
  try{const result=await api.patch<MessageResponse>(`/operations/issues/${issue.id}/state`,{state:'closed'});toasts.success('Issue fechada',result.message);await load()}catch(error){toasts.error('GitHub recusou a alteração',error instanceof ApiError?error.message:undefined)}finally{busyIssue.value=null}
}
watch(query,()=>{window.clearTimeout(debounceTimer);debounceTimer=window.setTimeout(()=>{page.value=1;void load()},350)})
onMounted(load);onBeforeUnmount(()=>window.clearTimeout(debounceTimer))
</script>

<template>
  <div class="operations-page">
    <section class="operations-heading"><div class="operations-heading-copy"><span>ACOMPANHAMENTO</span><h2>Issues abertas</h2><p>Issues reais coletadas do GitHub, com criação e fechamento diretamente pelo monitor.</p></div><div class="issue-heading-actions"><div v-if="response" class="operations-counter"><strong>{{response.total}}</strong><span>issues abertas</span></div><button class="button primary compact" @click="showCreate=true"><Plus :size="15"/>Nova issue</button></div></section>
    <OperationStatusBanner module-key="issues" @refreshed="load" />
    <section v-if="showCreate" class="issue-create-panel"><header><div><span class="eyebrow">CRIAR NO GITHUB</span><h3>Nova issue</h3></div><button class="icon-button" @click="showCreate=false"><X :size="16"/></button></header><div class="issue-form"><label class="field"><span>Repositório</span><select v-model="createForm.repository_id"><option v-for="repo in repoOptions" :key="repo.id" :value="repo.id">{{repo.full_name}}</option></select></label><label class="field"><span>Título</span><input v-model="createForm.title" maxlength="1000"/></label><label class="field full"><span>Descrição</span><textarea v-model="createForm.body" maxlength="65536"/></label><button class="button primary" :disabled="busyIssue==='create'" @click="createIssue"><Plus :size="15"/>Criar issue</button></div></section>
    <section class="operations-filter-panel"><label class="operations-search"><Search :size="16"/><input v-model="query" type="search" placeholder="Buscar issue, repositório, autor ou label..."/></label><button class="button secondary compact" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{spin:loading}"/>Atualizar</button></section>
    <section class="operations-panel">
      <div v-if="loading" class="operations-loading"><div v-for="index in 6" :key="index" class="skeleton"/></div>
      <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao carregar Issues" :message="errorMessage"><button class="button secondary compact" @click="load"><RefreshCw :size="15"/>Tentar novamente</button></EmptyState>
      <EmptyState v-else-if="!response?.items.length" :icon="CircleDotDashed" title="Nenhuma issue coletada" message="Confira a cobertura da coleta acima. Se houver repositórios não observados, sincronize e verifique Fila/permissões."/>
      <template v-else-if="response">
        <div class="operations-table-wrap"><table class="operations-table"><thead><tr><th>Repositório</th><th>Issue</th><th>Autor</th><th>Labels</th><th>Comentários</th><th>Atualização</th><th/></tr></thead><tbody><tr v-for="item in response.items" :key="item.id"><td><RouterLink :to="`/repositories/${item.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="item.repository_private" :size="14"/><Globe2 v-else :size="14"/></span><span><strong>{{item.repository_full_name.split('/').at(-1)}}</strong><small>{{item.repository_full_name.split('/')[0]}}</small></span></RouterLink></td><td><div class="operation-main"><strong>#{{item.number}} · {{item.title}}</strong><span>{{item.locked?'Bloqueada':'Aberta'}}</span></div></td><td>{{item.user_login||'desconhecido'}}</td><td><div class="issue-labels"><span v-for="label in item.labels" :key="label">{{label}}</span><small v-if="!item.labels.length">—</small></div></td><td><span class="comments"><MessageCircle :size="13"/>{{item.comments}}</span></td><td>{{formatRelative(item.github_updated_at||item.github_created_at)}}</td><td><div class="operation-actions"><button class="operation-action-button success" :disabled="busyIssue===item.id" title="Fechar issue" @click="closeIssue(item)"><CheckCircle2 :size="15"/></button><a class="operation-action-button" :href="item.html_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15"/></a></div></td></tr></tbody></table></div>
        <div class="operations-mobile-list"><article v-for="item in response.items" :key="item.id" class="operation-mobile-card"><div class="operation-mobile-card-header"><RouterLink :to="`/repositories/${item.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="item.repository_private" :size="14"/><Globe2 v-else :size="14"/></span><span><strong>{{item.repository_full_name.split('/').at(-1)}}</strong><small>{{item.repository_full_name.split('/')[0]}}</small></span></RouterLink><span class="comments"><MessageCircle :size="13"/>{{item.comments}}</span></div><div class="operation-mobile-card-body"><strong>#{{item.number}} · {{item.title}}</strong><span>{{item.user_login||'desconhecido'}} · {{formatRelative(item.github_updated_at||item.github_created_at)}}</span><div class="issue-labels"><span v-for="label in item.labels" :key="label">{{label}}</span></div></div><div class="operation-mobile-card-footer"><button class="button ghost compact" :disabled="busyIssue===item.id" @click="closeIssue(item)"><CheckCircle2 :size="14"/>Fechar</button><a class="operation-action-button" :href="item.html_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15"/></a></div></article></div>
        <PaginationBar :page="response.page" :pages="response.pages" :total="response.total" @change="changePage"/>
      </template>
    </section>
  </div>
</template>

<style scoped>
.issue-heading-actions{display:flex;align-items:center;gap:.7rem}.issue-create-panel{padding:1rem;border:1px solid var(--border);border-radius:.9rem;background:var(--surface);box-shadow:var(--shadow-sm)}.issue-create-panel header{display:flex;align-items:center;justify-content:space-between}.issue-create-panel h3{margin:.05rem 0;color:var(--text-strong)}.issue-form{display:grid;grid-template-columns:1fr 1.5fr auto;align-items:end;gap:.7rem;margin-top:.8rem}.issue-form .full{grid-column:1/-1}.issue-form textarea{min-height:120px}.issue-labels{display:flex;flex-wrap:wrap;gap:.25rem}.issue-labels span{padding:.15rem .35rem;border-radius:999px;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 8%,var(--surface));font-size:.54rem}.issue-labels small{color:var(--text-subtle)}.comments{display:inline-flex;align-items:center;gap:.25rem;color:var(--text-muted);font-size:.61rem}.operation-action-button.success{color:var(--success)}
@media(max-width:750px){.issue-heading-actions{align-items:stretch;flex-direction:column}.issue-form{grid-template-columns:1fr}.issue-form .full{grid-column:auto}.issue-form>.button{width:100%}}
</style>
