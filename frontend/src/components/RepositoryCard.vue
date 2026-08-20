<script setup lang="ts">
import { Code2, GitBranch, GitCommitHorizontal, GitPullRequest, Globe2, LockKeyhole } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import HealthRing from './HealthRing.vue'
import StatusBadge from './StatusBadge.vue'
import { formatRelative, shortSha } from '../services/format'
import type { Repository } from '../types/api'

defineProps<{ repository: Repository }>()
</script>

<template>
  <RouterLink :to="`/repositories/${repository.id}`" class="repo-card">
    <div class="repo-card-header">
      <div class="repo-identity">
        <div class="repo-icon"><Code2 :size="21" /></div>
        <div>
          <span class="repo-owner">{{ repository.owner }}</span>
          <h3>{{ repository.name }}</h3>
        </div>
      </div>
      <HealthRing :score="repository.health_score" :size="58" />
    </div>

    <p class="repo-description">{{ repository.description || 'Sem descrição cadastrada no GitHub.' }}</p>

    <div class="repo-badges">
      <StatusBadge :value="repository.health_status" health compact />
      <span class="privacy-badge">
        <LockKeyhole v-if="repository.private" :size="13" />
        <Globe2 v-else :size="13" />
        {{ repository.private ? 'Privado' : 'Público' }}
      </span>
    </div>

    <div class="repo-metrics">
      <span><GitBranch :size="14" />{{ repository.default_branch }}</span>
      <span><GitPullRequest :size="14" />{{ repository.open_pr_count }} PR</span>
      <span><GitCommitHorizontal :size="14" />{{ shortSha(repository.latest_commit_sha) }}</span>
    </div>

    <div class="repo-footer">
      <div>
        <span>Última atividade</span>
        <strong>{{ formatRelative(repository.pushed_at) }}</strong>
      </div>
      <div class="workflow-mini">
        <span>{{ repository.latest_workflow_name || 'Sem workflow' }}</span>
        <StatusBadge
          :value="repository.latest_workflow_conclusion || repository.latest_workflow_status"
          compact
        />
      </div>
    </div>
  </RouterLink>
</template>

<style scoped>
.repo-card { display:grid; gap:1rem; min-width:0; padding:1.05rem; color:inherit; text-decoration:none; border:1px solid var(--border); border-radius:var(--radius-xl); background:linear-gradient(145deg,var(--surface),var(--surface-raised)); box-shadow:var(--shadow-sm); transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease; }
.repo-card:hover { transform:translateY(-2px); border-color:color-mix(in srgb,var(--primary) 38%,var(--border)); box-shadow:var(--shadow-md); }
.repo-card-header,.repo-identity,.repo-badges,.repo-metrics,.repo-footer { display:flex; align-items:center; }
.repo-card-header { justify-content:space-between; gap:1rem; }
.repo-identity { gap:.72rem; min-width:0; }
.repo-icon { display:grid; place-items:center; width:2.5rem; height:2.5rem; border-radius:.82rem; color:var(--primary); background:color-mix(in srgb,var(--primary) 12%,var(--surface)); }
.repo-owner { display:block; color:var(--text-subtle); font-size:.7rem; }
h3 { margin:.08rem 0 0; overflow:hidden; color:var(--text-strong); font-size:1rem; text-overflow:ellipsis; white-space:nowrap; }
.repo-description { min-height:2.7em; margin:0; display:-webkit-box; overflow:hidden; color:var(--text-muted); font-size:.82rem; line-height:1.45; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.repo-badges { gap:.5rem; flex-wrap:wrap; }
.privacy-badge { display:inline-flex; align-items:center; gap:.35rem; color:var(--text-muted); font-size:.72rem; }
.repo-metrics { gap:.85rem; padding:.72rem 0; border-top:1px solid var(--border-soft); border-bottom:1px solid var(--border-soft); }
.repo-metrics span { display:inline-flex; align-items:center; gap:.35rem; color:var(--text-muted); font-size:.72rem; min-width:0; }
.repo-footer { justify-content:space-between; align-items:flex-end; gap:.8rem; }
.repo-footer > div { display:grid; gap:.2rem; }
.repo-footer span { color:var(--text-subtle); font-size:.66rem; }
.repo-footer strong { color:var(--text); font-size:.75rem; }
.workflow-mini { justify-items:end; text-align:right; min-width:0; }
.workflow-mini > span { max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
