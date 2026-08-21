<script setup lang="ts">
import { Code2, ExternalLink, GitBranch, GitCommitHorizontal, GitPullRequest, Globe2, LockKeyhole, RefreshCw, Trash2 } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import HealthRing from './HealthRing.vue'
import StatusBadge from './StatusBadge.vue'
import { formatRelative, shortSha } from '../services/format'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'
import type { MessageResponse, Repository, SyncResponse } from '../types/api'

const props = defineProps<{ repository: Repository }>()
const emit = defineEmits<{ changed: [] }>()
const toasts = useToastStore()

async function sync(): Promise<void> {
  try {
    const result = await api.post<SyncResponse>(`/repositories/${props.repository.id}/sync`)
    toasts.success('Sincronização enviada', `${result.message} Consulte a Fila para acompanhar.`)
  } catch (error) { toasts.error('Falha ao sincronizar', error instanceof ApiError ? error.message : undefined) }
}

async function togglePrivacy(): Promise<void> {
  const nextPrivate = !props.repository.private
  if (!window.confirm(`Tornar ${props.repository.full_name} ${nextPrivate ? 'privado' : 'público'} no GitHub?`)) return
  try {
    await api.patch<Repository>(`/repositories/${props.repository.id}/github`, { private: nextPrivate })
    toasts.success('Visibilidade atualizada', `O repositório agora é ${nextPrivate ? 'privado' : 'público'}.`)
    emit('changed')
  } catch (error) { toasts.error('GitHub recusou a alteração', error instanceof ApiError ? error.message : undefined) }
}

async function removeMonitoring(): Promise<void> {
  if (!window.confirm(`Parar de monitorar ${props.repository.full_name}? O repositório continuará intacto no GitHub.`)) return
  try {
    const result = await api.delete<MessageResponse>(`/repositories/${props.repository.id}/monitoring`)
    toasts.success('Monitoramento removido', result.message)
    emit('changed')
  } catch (error) { toasts.error('Falha ao remover do monitor', error instanceof ApiError ? error.message : undefined) }
}
</script>

<template>
  <article class="repo-card">
    <div class="repo-card-header"><div class="repo-identity"><div class="repo-icon"><Code2 :size="21" /></div><div><span class="repo-owner">{{ repository.owner }}</span><RouterLink :to="`/repositories/${repository.id}`"><h3>{{ repository.name }}</h3></RouterLink></div></div><HealthRing :score="repository.health_score" :size="58" /></div>
    <p class="repo-description">{{ repository.description || 'Sem descrição cadastrada no GitHub.' }}</p>
    <div class="repo-badges"><StatusBadge :value="repository.health_status" health compact /><span class="privacy-badge"><LockKeyhole v-if="repository.private" :size="13" /><Globe2 v-else :size="13" />{{ repository.private ? 'Privado' : 'Público' }}</span></div>
    <div class="repo-metrics"><span><GitBranch :size="14" />{{ repository.default_branch }}</span><span><GitPullRequest :size="14" />{{ repository.open_pr_count }} PR</span><span><GitCommitHorizontal :size="14" />{{ shortSha(repository.latest_commit_sha) }}</span></div>
    <div class="repo-footer"><div><span>Última atividade</span><strong>{{ formatRelative(repository.pushed_at) }}</strong></div><div class="workflow-mini"><span>{{ repository.latest_workflow_name || 'Sem workflow' }}</span><StatusBadge :value="repository.latest_workflow_conclusion || repository.latest_workflow_status" compact /></div></div>
    <div class="repo-actions"><button class="mini-action" title="Sincronizar" @click="sync"><RefreshCw :size="14" />Sincronizar</button><button class="mini-action" @click="togglePrivacy"><Globe2 v-if="repository.private" :size="14" /><LockKeyhole v-else :size="14" />{{ repository.private ? 'Publicar' : 'Privar' }}</button><a class="mini-action" :href="repository.html_url" target="_blank" rel="noopener"><ExternalLink :size="14" />GitHub</a><button class="mini-action danger" @click="removeMonitoring"><Trash2 :size="14" />Parar monitor</button></div>
  </article>
</template>

<style scoped>
.repo-card{display:grid;gap:1rem;min-width:0;padding:1.05rem;color:inherit;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--surface);box-shadow:var(--shadow-sm);transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}.repo-card:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--primary) 38%,var(--border));box-shadow:var(--shadow-md)}.repo-card-header,.repo-identity,.repo-badges,.repo-metrics,.repo-footer,.repo-actions{display:flex;align-items:center}.repo-card-header{justify-content:space-between;gap:1rem}.repo-identity{gap:.72rem;min-width:0}.repo-icon{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:.82rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.repo-owner{display:block;color:var(--text-muted);font-size:.7rem}.repo-identity a{text-decoration:none}h3{margin:.08rem 0 0;overflow:hidden;color:var(--text-strong);font-size:1rem;text-overflow:ellipsis;white-space:nowrap}.repo-description{min-height:2.7em;margin:0;display:-webkit-box;overflow:hidden;color:var(--text-muted);font-size:.82rem;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.repo-badges{gap:.5rem;flex-wrap:wrap}.privacy-badge{display:inline-flex;align-items:center;gap:.35rem;color:var(--text);font-size:.72rem}.repo-metrics{gap:.85rem;padding:.72rem 0;border-top:1px solid var(--border-soft);border-bottom:1px solid var(--border-soft)}.repo-metrics span{display:inline-flex;align-items:center;gap:.35rem;color:var(--text-muted);font-size:.72rem}.repo-footer{justify-content:space-between;align-items:flex-end;gap:.8rem}.repo-footer>div{display:grid;gap:.2rem}.repo-footer span{color:var(--text-muted);font-size:.66rem}.repo-footer strong{color:var(--text);font-size:.75rem}.workflow-mini{justify-items:end;text-align:right;min-width:0}.workflow-mini>span{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.repo-actions{flex-wrap:wrap;gap:.35rem;padding-top:.65rem;border-top:1px solid var(--border-soft)}.mini-action{display:inline-flex;align-items:center;justify-content:center;gap:.3rem;min-height:1.9rem;padding:.3rem .48rem;color:var(--text);font-size:.62rem;font-weight:750;text-decoration:none;border:1px solid var(--border);border-radius:.55rem;background:var(--surface-raised);cursor:pointer}.mini-action:hover{border-color:var(--primary);color:var(--primary-strong)}.mini-action.danger{color:var(--danger)}
@media(max-width:500px){.repo-actions{display:grid;grid-template-columns:1fr 1fr}.mini-action{width:100%}}
</style>
