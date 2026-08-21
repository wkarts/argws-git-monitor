<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertTriangle, Box, ExternalLink, GitBranch, Globe2, LockKeyhole, RefreshCw, Search } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import OperationStatusBanner from '../components/OperationStatusBanner.vue'
import PaginationBar from '../components/PaginationBar.vue'
import { ApiError, api } from '../services/api'
import { formatRelative } from '../services/format'
import type { OperationRelease, PaginatedResponse } from '../types/api'

const response=ref<PaginatedResponse<OperationRelease>|null>(null)
const loading=ref(true), errorMessage=ref(''), query=ref(''), mode=ref(''), page=ref(1)
let debounceTimer:number|undefined
function buildQuery():string{const p=new URLSearchParams({page:String(page.value),page_size:'30'});if(query.value.trim())p.set('q',query.value.trim());if(mode.value==='stable')p.set('prerelease','false');if(mode.value==='prerelease')p.set('prerelease','true');return p.toString()}
async function load():Promise<void>{loading.value=true;errorMessage.value='';try{response.value=await api.get<PaginatedResponse<OperationRelease>>(`/operations/releases?${buildQuery()}`)}catch(error){errorMessage.value=error instanceof ApiError?error.message:'Não foi possível carregar as releases.'}finally{loading.value=false}}
function changePage(target:number):void{page.value=target;void load();window.scrollTo({top:0,behavior:'smooth'})}
watch(mode,()=>{page.value=1;void load()});watch(query,()=>{window.clearTimeout(debounceTimer);debounceTimer=window.setTimeout(()=>{page.value=1;void load()},350)})
onMounted(load);onBeforeUnmount(()=>window.clearTimeout(debounceTimer))
</script>

<template>
  <div class="operations-page">
    <section class="operations-heading"><div class="operations-heading-copy"><span>VERSIONAMENTO</span><h2>Releases publicadas</h2><p>Consulte versões, pré-releases, branches de destino e links de publicação em todos os projetos.</p></div><div v-if="response" class="operations-counter"><strong>{{response.total}}</strong><span>releases</span></div></section>
    <OperationStatusBanner module-key="releases" @refreshed="load" />
    <section class="operations-filter-panel"><label class="operations-search"><Search :size="16"/><input v-model="query" type="search" placeholder="Buscar versão, nome, branch ou repositório..."/></label><select v-model="mode"><option value="">Todas as releases</option><option value="stable">Estáveis</option><option value="prerelease">Pré-releases</option></select><button class="button secondary compact" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{spin:loading}"/>Atualizar</button></section>
    <section class="operations-panel">
      <div v-if="loading" class="operations-loading"><div v-for="index in 6" :key="index" class="skeleton"/></div>
      <EmptyState v-else-if="errorMessage" :icon="AlertTriangle" title="Falha ao carregar Releases" :message="errorMessage"><button class="button secondary compact" @click="load"><RefreshCw :size="15"/>Tentar novamente</button></EmptyState>
      <EmptyState v-else-if="!response?.items.length" :icon="Box" title="Nenhuma release coletada" message="Confira a cobertura acima. Se a coleta não estiver completa, sincronize e verifique Fila/permissões."/>
      <template v-else-if="response">
        <div class="operations-table-wrap"><table class="operations-table"><thead><tr><th>Repositório</th><th>Versão</th><th>Tipo</th><th>Destino</th><th>Publicação</th><th/></tr></thead><tbody><tr v-for="release in response.items" :key="release.id"><td><RouterLink :to="`/repositories/${release.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="release.repository_private" :size="14"/><Globe2 v-else :size="14"/></span><span><strong>{{release.repository_full_name.split('/').at(-1)}}</strong><small>{{release.repository_full_name.split('/')[0]}}</small></span></RouterLink></td><td><div class="operation-main"><strong>{{release.tag_name}}</strong><span>{{release.name||'Release sem título'}}</span><small>{{release.draft?'rascunho':'publicada'}}</small></div></td><td><span class="release-mode" :class="{prerelease:release.prerelease,draft:release.draft}">{{release.draft?'Rascunho':release.prerelease?'Pré-release':'Estável'}}</span></td><td><span class="target-branch"><GitBranch :size="13"/>{{release.target_commitish||'main'}}</span></td><td>{{formatRelative(release.published_at||release.github_created_at)}}</td><td><a class="operation-action-button" :href="release.html_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15"/></a></td></tr></tbody></table></div>
        <div class="operations-mobile-list"><article v-for="release in response.items" :key="release.id" class="operation-mobile-card"><div class="operation-mobile-card-header"><RouterLink :to="`/repositories/${release.repository_id}`" class="operation-repository"><span class="operation-privacy"><LockKeyhole v-if="release.repository_private" :size="14"/><Globe2 v-else :size="14"/></span><span><strong>{{release.repository_full_name.split('/').at(-1)}}</strong><small>{{release.repository_full_name.split('/')[0]}}</small></span></RouterLink><span class="release-mode" :class="{prerelease:release.prerelease,draft:release.draft}">{{release.draft?'Rascunho':release.prerelease?'Pré-release':'Estável'}}</span></div><div class="operation-mobile-card-body"><strong>{{release.tag_name}}</strong><span>{{release.name||'Release sem título'}}</span><small>{{release.target_commitish||'main'}} · {{formatRelative(release.published_at||release.github_created_at)}}</small></div><div class="operation-mobile-card-footer"><span>{{release.draft?'Ainda não publicada':'Disponível no GitHub'}}</span><a class="operation-action-button" :href="release.html_url" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15"/></a></div></article></div>
        <PaginationBar :page="response.page" :pages="response.pages" :total="response.total" @change="changePage"/>
      </template>
    </section>
  </div>
</template>

<style scoped>.release-mode{display:inline-flex;padding:.2rem .48rem;color:var(--success);border:1px solid color-mix(in srgb,var(--success) 24%,var(--border));border-radius:999px;background:color-mix(in srgb,var(--success) 8%,var(--surface));font-size:.57rem;font-weight:780;white-space:nowrap}.release-mode.prerelease{color:var(--warning);border-color:color-mix(in srgb,var(--warning) 24%,var(--border));background:color-mix(in srgb,var(--warning) 8%,var(--surface))}.release-mode.draft{color:var(--text-muted);border-color:var(--border);background:var(--surface-soft)}.target-branch{display:inline-flex;align-items:center;gap:.32rem;color:var(--primary-strong);font-size:.61rem}</style>
