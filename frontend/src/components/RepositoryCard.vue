<script setup lang="ts">
import { ref } from 'vue'
import { Ban, Code2, DatabaseBackup, ExternalLink, GitBranch, GitCommitHorizontal, GitPullRequest, Globe2, LockKeyhole, Power, RefreshCw, Wrench, XCircle } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import HealthRing from './HealthRing.vue'
import StatusBadge from './StatusBadge.vue'
import { formatRelative, shortSha } from '../services/format'
import { ApiError, api } from '../services/api'
import { useDialogStore } from '../stores/dialog'
import { useToastStore } from '../stores/toast'
import type { MessageResponse, Repository, SyncResponse } from '../types/api'

interface ActionsState {
  repository_id: string
  full_name: string
  enabled: boolean
  allowed_actions: string | null
  sha_pinning_required: boolean | null
}

interface ActionsUpdateResponse {
  enabled: boolean
  cancelled_runs: number[]
  cancel_errors: Array<{ run_id: number; status_code: number | null }>
  message: string
}

const props = defineProps<{ repository: Repository }>()
const emit = defineEmits<{ changed: [] }>()
const dialogs = useDialogStore()
const toasts = useToastStore()
const actionsBusy = ref(false)

function healthTitle(): string {
  if (props.repository.health_status === 'unknown' || !props.repository.health_coverage) {
    return 'Saúde não calculada: aguardando a primeira sincronização detalhada.'
  }
  const components = Object.values(props.repository.health_components || {})
    .map((item) => `${item.label}: ${item.evaluated ? `${item.points}/${item.weight}` : 'N/A'} · ${item.detail}`)
    .join('\n')
  return `Saúde ${props.repository.health_score}% · cobertura ${props.repository.health_coverage}%\n${components}`
}

async function sync(): Promise<void> {
  try {
    const result = await api.post<SyncResponse>(`/repositories/${props.repository.id}/sync`)
    toasts.success('Reconciliação enviada', `${result.message} O estado imediato continua chegando em tempo real.`)
  } catch (error) { toasts.error('Falha ao sincronizar', error instanceof ApiError ? error.message : undefined) }
}

async function toggleActions(): Promise<void> {
  if (actionsBusy.value) return
  actionsBusy.value = true
  try {
    const state = await api.get<ActionsState>(`/repository-controls/${props.repository.id}/actions`)
    const nextEnabled = !state.enabled
    const confirmed = await dialogs.confirm({
      title: nextEnabled ? 'Ativar GitHub Actions?' : 'Desativar GitHub Actions?',
      message: nextEnabled
        ? `Os workflows de ${props.repository.full_name} voltarão a aceitar execuções.`
        : `Os workflows de ${props.repository.full_name} serão desativados. Execuções em fila ou andamento também terão cancelamento solicitado quando possível.`,
      tone: nextEnabled ? 'info' : 'warning',
      confirmLabel: nextEnabled ? 'Ativar Actions' : 'Desativar Actions',
    })
    if (!confirmed) return
    const result = await api.put<ActionsUpdateResponse>(`/repository-controls/${props.repository.id}/actions`, {
      enabled: nextEnabled,
      cancel_in_progress: true
    })
    const cancellation = result.cancelled_runs.length
      ? ` ${result.cancelled_runs.length} execução(ões) em andamento tiveram cancelamento solicitado.`
      : ''
    toasts.success(nextEnabled ? 'Actions ativado' : 'Actions desativado', `${result.message}${cancellation}`)
    emit('changed')
  } catch (error) {
    toasts.error('Não foi possível alterar GitHub Actions', error instanceof ApiError ? error.message : undefined)
  } finally {
    actionsBusy.value = false
  }
}

async function togglePrivacy(): Promise<void> {
  const nextPrivate = !props.repository.private
  const confirmed = await dialogs.confirm({
    title: nextPrivate ? 'Tornar repositório privado?' : 'Tornar repositório público?',
    message: `${props.repository.full_name} será alterado no próprio GitHub.`,
    tone: nextPrivate ? 'warning' : 'danger',
    confirmLabel: nextPrivate ? 'Tornar privado' : 'Tornar público',
  })
  if (!confirmed) return
  try {
    await api.patch<Repository>(`/repositories/${props.repository.id}/github`, { private: nextPrivate })
    toasts.success('Visibilidade atualizada', `O repositório agora é ${nextPrivate ? 'privado' : 'público'}.`)
    emit('changed')
  } catch (error) { toasts.error('GitHub recusou a alteração', error instanceof ApiError ? error.message : undefined) }
}

async function removeMonitoring(): Promise<void> {
  const confirmed = await dialogs.confirm({
    title: 'Ignorar repositório no Git Monitor?',
    message: `${props.repository.full_name} continuará intacto no GitHub, mas desaparecerá do monitor e não voltará nas próximas sincronizações. Você poderá reativá-lo depois pela lista de ignorados.`,
    tone: 'warning',
    confirmLabel: 'Ignorar repositório',
  })
  if (!confirmed) return
  try {
    const result = await api.post<MessageResponse>(`/repository-controls/${props.repository.id}/blacklist`)
    toasts.success('Repositório ignorado', result.message)
    emit('changed')
  } catch (error) { toasts.error('Falha ao adicionar à lista negra', error instanceof ApiError ? error.message : undefined) }
}

async function deleteFromGithub(): Promise<void> {
  const confirmation = await dialogs.prompt({
    title: 'Excluir definitivamente no GitHub?',
    message: 'Esta ação remove o repositório remoto e não pode ser desfeita pelo Git Monitor. Backups existentes não substituem uma confirmação consciente desta exclusão.',
    tone: 'danger',
    confirmLabel: 'Excluir definitivamente',
    promptLabel: 'Confirmação obrigatória',
    promptExpected: props.repository.full_name,
    promptPlaceholder: props.repository.full_name,
  })
  if (confirmation === null) return
  try {
    const result = await api.post<MessageResponse>(`/repositories/${props.repository.id}/delete-github`, { confirmation })
    toasts.success('Repositório excluído', result.message)
    emit('changed')
  } catch (error) { toasts.error('GitHub recusou a exclusão', error instanceof ApiError ? error.message : undefined) }
}
</script>

<template>
  <article class="repo-card">
    <div class="repo-card-header"><div class="repo-identity"><div class="repo-icon"><Code2 :size="21" /></div><div><span class="repo-owner">{{ repository.owner }}</span><RouterLink :to="`/repositories/${repository.id}`"><h3>{{ repository.name }}</h3></RouterLink></div></div><div class="health-wrap" :title="healthTitle()"><HealthRing :score="repository.health_status === 'unknown' ? 0 : repository.health_score" :size="58" /><small v-if="repository.health_status === 'unknown'">sem dados</small><small v-else>{{ repository.health_coverage }}% cobertura</small></div></div>
    <p class="repo-description">{{ repository.description || 'Sem descrição cadastrada no GitHub.' }}</p>
    <div class="repo-badges"><StatusBadge :value="repository.health_status" health compact /><span class="privacy-badge"><LockKeyhole v-if="repository.private" :size="13" /><Globe2 v-else :size="13" />{{ repository.private ? 'Privado' : 'Público' }}</span></div>
    <div class="repo-metrics"><span><GitBranch :size="14" />{{ repository.default_branch }}</span><span><GitPullRequest :size="14" />{{ repository.open_pr_count }} PR</span><span><GitCommitHorizontal :size="14" />{{ shortSha(repository.latest_commit_sha) }}</span></div>
    <div class="repo-footer"><div :title="repository.last_activity_summary || undefined"><span>Última atividade observada</span><strong>{{ formatRelative(repository.last_activity_at) }}</strong><small>{{ repository.last_activity_type || (repository.activity_observed_at ? 'sem evento recente' : 'aguardando leitura') }}</small></div><div class="workflow-mini"><span>{{ repository.latest_workflow_name || 'Sem workflow' }}</span><StatusBadge :value="repository.latest_workflow_conclusion || repository.latest_workflow_status" compact /></div></div>
    <div class="repo-actions"><button class="mini-action" title="Reconciliação completa" @click="sync"><RefreshCw :size="14" />Sincronizar</button><button class="mini-action" :disabled="actionsBusy" title="Ativar ou desativar GitHub Actions" @click="toggleActions"><Power :size="14" />{{ actionsBusy ? 'Actions…' : 'Actions ON/OFF' }}</button><RouterLink class="mini-action" :to="`/github-tools?repository=${repository.id}`"><Wrench :size="14" />Ferramentas</RouterLink><RouterLink class="mini-action" :to="`/backup-complete?repository=${repository.id}`"><DatabaseBackup :size="14" />Backup completo</RouterLink><button class="mini-action" @click="togglePrivacy"><Globe2 v-if="repository.private" :size="14" /><LockKeyhole v-else :size="14" />{{ repository.private ? 'Publicar' : 'Privar' }}</button><a class="mini-action" :href="repository.html_url" target="_blank" rel="noopener"><ExternalLink :size="14" />GitHub</a><button class="mini-action danger" @click="removeMonitoring"><Ban :size="14" />Ignorar</button><button class="mini-action destructive" @click="deleteFromGithub"><XCircle :size="14" />Excluir GitHub</button></div>
  </article>
</template>

<style scoped>
.repo-card{display:grid;gap:1rem;min-width:0;padding:1.05rem;color:inherit;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--surface);box-shadow:var(--shadow-sm);transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}.repo-card:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--primary) 38%,var(--border));box-shadow:var(--shadow-md)}.repo-card-header,.repo-identity,.repo-badges,.repo-metrics,.repo-footer,.repo-actions{display:flex;align-items:center}.repo-card-header{justify-content:space-between;gap:1rem}.repo-identity{gap:.72rem;min-width:0}.repo-icon{display:grid;place-items:center;width:2.5rem;height:2.5rem;border-radius:.82rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 10%,var(--surface))}.repo-owner{display:block;color:var(--text-muted);font-size:.7rem}.repo-identity a{text-decoration:none}h3{margin:.08rem 0 0;overflow:hidden;color:var(--text-strong);font-size:1rem;text-overflow:ellipsis;white-space:nowrap}.health-wrap{display:grid;justify-items:center;gap:.15rem;cursor:help}.health-wrap small{color:var(--text-subtle);font-size:.52rem}.repo-description{min-height:2.7em;margin:0;display:-webkit-box;overflow:hidden;color:var(--text-muted);font-size:.82rem;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}.repo-badges{gap:.5rem;flex-wrap:wrap}.privacy-badge{display:inline-flex;align-items:center;gap:.35rem;color:var(--text);font-size:.72rem}.repo-metrics{gap:.85rem;padding:.72rem 0;border-top:1px solid var(--border-soft);border-bottom:1px solid var(--border-soft)}.repo-metrics span{display:inline-flex;align-items:center;gap:.35rem;color:var(--text-muted);font-size:.72rem}.repo-footer{justify-content:space-between;align-items:flex-end;gap:.8rem}.repo-footer>div{display:grid;gap:.2rem}.repo-footer span{color:var(--text-muted);font-size:.66rem}.repo-footer strong{color:var(--text);font-size:.75rem}.repo-footer small{color:var(--text-subtle);font-size:.55rem}.workflow-mini{justify-items:end;text-align:right;min-width:0}.workflow-mini>span{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.repo-actions{flex-wrap:wrap;gap:.35rem;padding-top:.65rem;border-top:1px solid var(--border-soft)}.mini-action{display:inline-flex;align-items:center;justify-content:center;gap:.3rem;min-height:1.9rem;padding:.3rem .48rem;color:var(--text);font-size:.62rem;font-weight:750;text-decoration:none;border:1px solid var(--border);border-radius:.55rem;background:var(--surface-raised);cursor:pointer}.mini-action:hover{border-color:var(--primary);color:var(--primary-strong)}.mini-action:disabled{opacity:.55;cursor:wait}.mini-action.danger{color:var(--warning)}.mini-action.destructive{color:var(--danger);border-color:color-mix(in srgb,var(--danger) 24%,var(--border));background:color-mix(in srgb,var(--danger) 5%,var(--surface))}
@media(max-width:500px){.repo-actions{display:grid;grid-template-columns:1fr 1fr}.mini-action{width:100%}}
</style>
