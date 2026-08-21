<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  Boxes, FileCode2, GitBranch, GitFork, Package, Play, RefreshCw, Rocket, Save,
  Search, Tag, Trash2, UploadCloud
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'
import type {
  GitHubConnection, GitHubTreeItem, PackageVersion, PaginatedResponse, Repository, ToolResult
} from '../types/api'

const toasts = useToastStore()
const loading = ref(true)
const busy = ref('')
const connections = ref<GitHubConnection[]>([])
const repositories = ref<Repository[]>([])
const tree = ref<GitHubTreeItem[]>([])
const packageVersions = ref<PackageVersion[]>([])
const selectedConnectionId = ref('')
const selectedRepositoryId = ref('')
const repositoryQuery = ref('')

const branchForm = reactive({ branch: 'develop', base_branch: '', set_default: false })
const treeForm = reactive({ branch: 'main', prefix: '' })
const fileForm = reactive({ branch: 'main', path: 'README.md', message: 'chore: atualiza arquivo pelo ARGWS Git Monitor', content: '', overwrite: true })
const bootstrapForm = reactive({ branch: 'main', overwrite: false, include_dockerfile: false, include_workflow: true })
const releaseForm = reactive({ tag_name: 'v0.1.0', target_commitish: 'main', name: '', body: '', prerelease: false })
const workflowForm = reactive({ workflow: 'docker-publish.yml', ref: 'main' })
const packageForm = reactive({ owner: '', package_name: '' })

const selectedRepository = computed(() => repositories.value.find((item) => item.id === selectedRepositoryId.value) || null)
const selectedConnection = computed(() => connections.value.find((item) => item.id === selectedConnectionId.value) || null)
const filteredRepositories = computed(() => {
  const query = repositoryQuery.value.trim().toLowerCase()
  const source = selectedConnectionId.value
    ? repositories.value.filter((item) => item.connection_id === selectedConnectionId.value)
    : repositories.value
  if (!query) return source
  return source.filter((item) => item.full_name.toLowerCase().includes(query))
})

async function loadRepositories(): Promise<Repository[]> {
  const all: Repository[] = []
  let page = 1
  let pages = 1
  do {
    const response = await api.get<PaginatedResponse<Repository>>(`/repositories?page=${page}&page_size=100`)
    all.push(...response.items)
    pages = response.pages
    page += 1
  } while (page <= pages)
  return all
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [loadedConnections, loadedRepositories] = await Promise.all([
      api.get<GitHubConnection[]>('/github/connections'),
      loadRepositories()
    ])
    connections.value = loadedConnections.filter((item) => item.status !== 'demo')
    repositories.value = loadedRepositories
    if (!selectedConnectionId.value && connections.value.length) selectedConnectionId.value = connections.value[0].id
    if (!selectedRepositoryId.value && filteredRepositories.value.length) selectedRepositoryId.value = filteredRepositories.value[0].id
  } catch (error) {
    toasts.error('Falha ao carregar GitHub Tools', error instanceof ApiError ? error.message : undefined)
  } finally { loading.value = false }
}

watch(selectedConnectionId, () => {
  const candidate = repositories.value.find((item) => item.connection_id === selectedConnectionId.value)
  if (candidate) selectedRepositoryId.value = candidate.id
  packageForm.owner = selectedConnection.value?.github_login || ''
})
watch(selectedRepository, (repository) => {
  if (!repository) return
  treeForm.branch = repository.default_branch
  fileForm.branch = repository.default_branch
  bootstrapForm.branch = repository.default_branch
  releaseForm.target_commitish = repository.default_branch
  workflowForm.ref = repository.default_branch
  packageForm.package_name = repository.name
  packageForm.owner = repository.owner
})

async function run(key: string, action: () => Promise<void>): Promise<void> {
  busy.value = key
  try { await action() }
  catch (error) { toasts.error('Operação recusada', error instanceof ApiError ? error.message : undefined) }
  finally { busy.value = '' }
}

async function createBranch(): Promise<void> {
  if (!selectedRepository.value) return
  await run('branch', async () => {
    const result = await api.post<{ branch: string; created: boolean; set_default: boolean }>(
      `/github-tools/repositories/${selectedRepository.value!.id}/branches`,
      { ...branchForm, base_branch: branchForm.base_branch || null }
    )
    toasts.success(result.created ? 'Branch criada' : 'Branch já existia', `${result.branch}${result.set_default ? ' é agora a padrão.' : ''}`)
    await load()
  })
}

async function loadTree(): Promise<void> {
  if (!selectedRepository.value) return
  await run('tree', async () => {
    const params = new URLSearchParams({ branch: treeForm.branch })
    if (treeForm.prefix.trim()) params.set('prefix', treeForm.prefix.trim())
    tree.value = await api.get<GitHubTreeItem[]>(`/github-tools/repositories/${selectedRepository.value!.id}/tree?${params}`)
  })
}

async function saveFile(): Promise<void> {
  if (!selectedRepository.value) return
  await run('file', async () => {
    const result = await api.put<ToolResult>(`/github-tools/repositories/${selectedRepository.value!.id}/files`, fileForm)
    toasts.success('Arquivo salvo', result.message)
    await loadTree()
  })
}

async function deletePath(): Promise<void> {
  const repository = selectedRepository.value
  if (!repository || !treeForm.prefix.trim()) {
    toasts.warning('Informe um caminho', 'Digite o arquivo ou diretório no campo Filtro/caminho.')
    return
  }
  const expected = `${repository.full_name}:${treeForm.prefix.trim().replace(/^\/+|\/+$/g, '')}`
  const confirmation = window.prompt(`Remover este caminho do GitHub?\n\nDigite exatamente:\n${expected}`)
  if (confirmation !== expected) return
  await run('delete-path', async () => {
    const result = await api.post<ToolResult>(`/github-tools/repositories/${repository.id}/delete-path`, {
      branch: treeForm.branch, path: treeForm.prefix, confirmation
    })
    toasts.success('Caminho removido', result.message)
    await loadTree()
  })
}

async function bootstrap(): Promise<void> {
  if (!selectedRepository.value) return
  await run('bootstrap', async () => {
    const result = await api.post<ToolResult>(`/github-tools/repositories/${selectedRepository.value!.id}/bootstrap`, bootstrapForm)
    toasts.success('Estrutura inicial aplicada', result.message)
  })
}

async function createRelease(): Promise<void> {
  if (!selectedRepository.value) return
  await run('release', async () => {
    const result = await api.post<ToolResult>(`/github-tools/repositories/${selectedRepository.value!.id}/releases`, {
      ...releaseForm, name: releaseForm.name || null, body: releaseForm.body || null
    })
    toasts.success('Release criada', result.message)
  })
}

async function dispatchWorkflow(): Promise<void> {
  if (!selectedRepository.value) return
  await run('dispatch', async () => {
    const result = await api.post<ToolResult>(`/github-tools/repositories/${selectedRepository.value!.id}/dispatch`, workflowForm)
    toasts.success('Workflow iniciado', result.message)
  })
}

async function loadPackages(): Promise<void> {
  if (!selectedConnection.value || !packageForm.package_name.trim()) return
  await run('packages', async () => {
    const owner = encodeURIComponent(packageForm.owner || selectedConnection.value!.github_login)
    const name = encodeURIComponent(packageForm.package_name.trim())
    packageVersions.value = await api.get<PackageVersion[]>(`/github-tools/connections/${selectedConnection.value!.id}/packages/${name}/versions?owner=${owner}`)
  })
}

async function deletePackageVersion(version: PackageVersion): Promise<void> {
  if (!selectedConnection.value) return
  const owner = packageForm.owner || selectedConnection.value.github_login
  const expected = `${owner}/${packageForm.package_name}:${version.id}`
  const confirmation = window.prompt(`Excluir esta versão do GHCR?\nTags: ${version.tags.join(', ') || 'sem tags'}\n\nDigite exatamente:\n${expected}`)
  if (confirmation !== expected) return
  await run(`package-${version.id}`, async () => {
    const result = await api.post<ToolResult>(
      `/github-tools/connections/${selectedConnection.value!.id}/packages/${encodeURIComponent(packageForm.package_name)}/versions/${version.id}/delete?owner=${encodeURIComponent(owner)}`,
      { confirmation }
    )
    toasts.success('Versão removida', result.message)
    await loadPackages()
  })
}

async function deletePackage(): Promise<void> {
  if (!selectedConnection.value || !packageForm.package_name) return
  const owner = packageForm.owner || selectedConnection.value.github_login
  const expected = `${owner}/${packageForm.package_name}`
  const confirmation = window.prompt(`EXCLUSÃO DO PACOTE GHCR.\nDigite exatamente:\n${expected}`)
  if (confirmation !== expected) return
  await run('delete-package', async () => {
    const result = await api.post<ToolResult>(
      `/github-tools/connections/${selectedConnection.value!.id}/packages/${encodeURIComponent(packageForm.package_name)}/delete?owner=${encodeURIComponent(owner)}`,
      { confirmation }
    )
    packageVersions.value = []
    toasts.success('Pacote removido', result.message)
  })
}

onMounted(load)
</script>

<template>
  <div class="page-stack tools-page">
    <section class="page-heading">
      <div><span class="eyebrow">GITHUB ONLINE + GHCR</span><h2>GitHub Tools</h2><p>Gerenciamento online de branches, arquivos, estrutura inicial, releases, workflows e pacotes GHCR — portado da ferramenta PowerShell para FastAPI/Vue.</p></div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16" />Atualizar</button>
    </section>

    <section class="control-strip">
      <label class="field"><span>Conexão GitHub</span><select v-model="selectedConnectionId"><option v-for="connection in connections" :key="connection.id" :value="connection.id">{{ connection.name }} · @{{ connection.github_login }}</option></select></label>
      <label class="field search-repo"><span>Filtrar repositório</span><div class="input-with-icon"><Search :size="15" /><input v-model="repositoryQuery" placeholder="owner/repo" /></div></label>
      <label class="field"><span>Repositório</span><select v-model="selectedRepositoryId"><option v-for="repository in filteredRepositories" :key="repository.id" :value="repository.id">{{ repository.full_name }}</option></select></label>
    </section>

    <div v-if="!selectedRepository" class="empty-tools"><Boxes :size="28" /><strong>Nenhum repositório monitorado selecionado</strong><p>Conecte o GitHub e monitore ao menos um repositório.</p></div>

    <template v-else>
      <section class="tool-grid">
        <article class="tool-card">
          <header><GitBranch :size="19" /><div><strong>Branches</strong><span>Criar e definir branch padrão</span></div></header>
          <div class="form-grid"><label class="field"><span>Nova branch</span><input v-model="branchForm.branch" /></label><label class="field"><span>Base (vazio = padrão atual)</span><input v-model="branchForm.base_branch" /></label></div>
          <label class="check"><input v-model="branchForm.set_default" type="checkbox" /> Definir como branch padrão</label>
          <button class="button primary" :disabled="busy==='branch'" @click="createBranch"><GitFork :size="15" />Criar/garantir branch</button>
        </article>

        <article class="tool-card">
          <header><Rocket :size="19" /><div><strong>Bootstrap online</strong><span>README, .gitignore, Dockerfile opcional e workflow GHCR</span></div></header>
          <label class="field"><span>Branch</span><input v-model="bootstrapForm.branch" /></label>
          <div class="check-row"><label class="check"><input v-model="bootstrapForm.include_workflow" type="checkbox" /> Workflow Docker/GHCR</label><label class="check"><input v-model="bootstrapForm.include_dockerfile" type="checkbox" /> Dockerfile placeholder</label><label class="check"><input v-model="bootstrapForm.overwrite" type="checkbox" /> Sobrescrever existentes</label></div>
          <button class="button primary" :disabled="busy==='bootstrap'" @click="bootstrap"><UploadCloud :size="15" />Aplicar estrutura</button>
        </article>

        <article class="tool-card">
          <header><Tag :size="19" /><div><strong>Release</strong><span>Criar tag/release diretamente no GitHub</span></div></header>
          <div class="form-grid"><label class="field"><span>Tag</span><input v-model="releaseForm.tag_name" /></label><label class="field"><span>Target</span><input v-model="releaseForm.target_commitish" /></label></div>
          <label class="field"><span>Nome</span><input v-model="releaseForm.name" placeholder="Opcional" /></label><label class="field"><span>Notas</span><textarea v-model="releaseForm.body" placeholder="Vazio = notas automáticas" /></label>
          <label class="check"><input v-model="releaseForm.prerelease" type="checkbox" /> Pré-release</label>
          <button class="button primary" :disabled="busy==='release'" @click="createRelease"><Tag :size="15" />Criar release</button>
        </article>

        <article class="tool-card">
          <header><Play :size="19" /><div><strong>Workflow dispatch</strong><span>Executar workflow por arquivo ou ID</span></div></header>
          <label class="field"><span>Workflow</span><input v-model="workflowForm.workflow" placeholder="docker-publish.yml" /></label><label class="field"><span>Ref</span><input v-model="workflowForm.ref" /></label>
          <button class="button primary" :disabled="busy==='dispatch'" @click="dispatchWorkflow"><Play :size="15" />Executar workflow</button>
        </article>
      </section>

      <section class="tool-card wide">
        <header><FileCode2 :size="19" /><div><strong>Arquivos online</strong><span>Listar árvore, criar/atualizar arquivos e remover caminho recursivamente</span></div></header>
        <div class="form-grid three"><label class="field"><span>Branch</span><input v-model="treeForm.branch" /></label><label class="field span-2"><span>Filtro/caminho</span><input v-model="treeForm.prefix" placeholder=".github/workflows ou arquivo.txt" /></label></div>
        <div class="button-row"><button class="button secondary" :disabled="busy==='tree'" @click="loadTree"><Search :size="15" />Listar árvore</button><button class="button ghost danger-text" :disabled="busy==='delete-path'" @click="deletePath"><Trash2 :size="15" />Excluir caminho</button></div>
        <div v-if="tree.length" class="tree-list"><div v-for="item in tree.slice(0,200)" :key="item.path"><code>{{ item.path }}</code><span>{{ item.type }}<template v-if="item.size"> · {{ item.size }} bytes</template></span></div></div>
        <div class="file-editor"><div class="form-grid"><label class="field"><span>Branch</span><input v-model="fileForm.branch" /></label><label class="field"><span>Caminho do arquivo</span><input v-model="fileForm.path" /></label></div><label class="field"><span>Mensagem do commit</span><input v-model="fileForm.message" /></label><label class="field"><span>Conteúdo UTF-8</span><textarea v-model="fileForm.content" class="code-editor" spellcheck="false" /></label><label class="check"><input v-model="fileForm.overwrite" type="checkbox" /> Atualizar se o arquivo já existir</label><button class="button primary" :disabled="busy==='file'" @click="saveFile"><Save :size="15" />Salvar no GitHub</button></div>
      </section>

      <section class="tool-card wide">
        <header><Package :size="19" /><div><strong>GitHub Container Registry</strong><span>Listar tags/versões e remover versões ou pacote inteiro</span></div></header>
        <div class="form-grid three"><label class="field"><span>Owner/organização</span><input v-model="packageForm.owner" /></label><label class="field span-2"><span>Nome do pacote</span><input v-model="packageForm.package_name" /></label></div>
        <div class="button-row"><button class="button secondary" :disabled="busy==='packages'" @click="loadPackages"><RefreshCw :size="15" />Consultar GHCR</button><button class="button ghost danger-text" :disabled="busy==='delete-package'" @click="deletePackage"><Trash2 :size="15" />Excluir pacote</button></div>
        <div v-if="packageVersions.length" class="package-list"><article v-for="version in packageVersions" :key="version.id"><div><strong>#{{ version.id }}</strong><span>{{ version.tags.join(', ') || 'sem tags' }}</span><small>{{ version.name }}</small></div><button class="button ghost compact danger-text" @click="deletePackageVersion(version)"><Trash2 :size="14" />Remover versão</button></article></div><p v-else class="tool-hint">Consulte o pacote para listar versões e tags. Para excluir, o token precisa de permissão de packages.</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.control-strip{display:grid;grid-template-columns:1fr 1fr 1.5fr;gap:.8rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.tool-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.tool-card{display:grid;align-content:start;gap:.8rem;padding:1rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-sm)}.tool-card.wide{width:100%}.tool-card header{display:flex;align-items:center;gap:.65rem;padding-bottom:.7rem;border-bottom:1px solid var(--border-soft);color:var(--primary-strong)}.tool-card header div{display:grid}.tool-card header strong{color:var(--text-strong)}.tool-card header span{color:var(--text-muted);font-size:.68rem}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem}.form-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.span-2{grid-column:span 2}.check-row,.button-row{display:flex;flex-wrap:wrap;gap:.65rem}.check{display:flex;align-items:center;gap:.4rem;color:var(--text-muted);font-size:.72rem}.check input{accent-color:var(--primary)}.tree-list{max-height:300px;overflow:auto;border:1px solid var(--border-soft);border-radius:.7rem;background:var(--surface-soft)}.tree-list div{display:flex;justify-content:space-between;gap:1rem;padding:.45rem .65rem;border-bottom:1px solid var(--border-soft);font-size:.68rem}.tree-list code{color:var(--text)}.tree-list span{color:var(--text-subtle)}.file-editor{display:grid;gap:.7rem;padding-top:.8rem;border-top:1px solid var(--border-soft)}.code-editor{min-height:220px!important;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.72rem}.package-list{display:grid;border:1px solid var(--border-soft);border-radius:.8rem;overflow:hidden}.package-list article{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.7rem;border-bottom:1px solid var(--border-soft)}.package-list article:last-child{border-bottom:0}.package-list article div{display:grid}.package-list span{color:var(--primary-strong);font-size:.7rem}.package-list small,.tool-hint{color:var(--text-muted);font-size:.68rem}.tool-hint{margin:0}.empty-tools{display:grid;place-items:center;gap:.4rem;padding:4rem;border:1px dashed var(--border);border-radius:1rem;color:var(--text-muted);text-align:center;background:var(--surface)}.empty-tools strong{color:var(--text-strong)}.danger-text{color:var(--danger)!important}
@media(max-width:900px){.control-strip,.tool-grid{grid-template-columns:1fr}.form-grid.three{grid-template-columns:1fr}.span-2{grid-column:auto}}@media(max-width:600px){.form-grid{grid-template-columns:1fr}.control-strip{padding:.8rem}.package-list article{align-items:stretch;flex-direction:column}.package-list .button{width:100%}}
</style>
