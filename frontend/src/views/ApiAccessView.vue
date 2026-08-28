<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Activity, Braces, Check, Copy, ExternalLink, KeyRound, RefreshCw,
  ShieldCheck, Terminal, Trash2, Webhook
} from 'lucide-vue-next'
import { ApiError, api } from '../services/api'
import { useToastStore } from '../stores/toast'

interface ApiScope { scope:string; description:string }
interface ApiKeyItem { id:string; name:string; prefix:string; scopes:string[]; enabled:boolean; expires_at:string|null; last_used_at:string|null; created_at:string; token?:string; warning?:string }

const toasts = useToastStore()
const loading = ref(true)
const busy = ref('')
const scopes = ref<ApiScope[]>([])
const keys = ref<ApiKeyItem[]>([])
const createdToken = ref('')
const copied = ref(false)
const formOpen = ref(false)
const form = reactive({ name:'Integração Git Monitor', scopes:['monitoring:read','repositories:read'] as string[], expires_at:'' })

const externalBase = computed(() => `${window.location.origin}/api/v1/external/v1`)
const docsUrl = computed(() => `${window.location.origin}/api/v1/docs`)
const enabledKeys = computed(() => keys.value.filter((item) => item.enabled))
const usedKeys = computed(() => keys.value.filter((item) => item.last_used_at))
const uniqueScopes = computed(() => new Set(keys.value.flatMap((item) => item.scopes)).size)
const curlExample = computed(() => `curl -H "X-API-Key: agm_SEU_TOKEN" \\\n  "${externalBase.value}/status"`)
const repoExample = computed(() => `curl -H "Authorization: Bearer agm_SEU_TOKEN" \\\n  "${externalBase.value}/repositories"`)

function errorMessage(error:unknown):string { return error instanceof ApiError ? error.message : String(error) }
function when(value:string|null):string { return value ? new Date(value).toLocaleString('pt-BR') : 'Nunca' }
function relativeExpiry(value:string|null):string {
  if(!value) return 'Sem expiração'
  const diff=new Date(value).getTime()-Date.now()
  if(diff<=0) return 'Expirada'
  const days=Math.ceil(diff/86400000)
  return days===1 ? 'Expira amanhã' : `Expira em ${days} dias`
}

async function load():Promise<void> {
  loading.value=true
  try {
    const [scopeData,keyData]=await Promise.all([
      api.get<ApiScope[]>('/api-access/scopes'),
      api.get<ApiKeyItem[]>('/api-access/keys')
    ])
    scopes.value=scopeData
    keys.value=keyData
  } catch(error){ toasts.error('Falha ao carregar API & Integrações',errorMessage(error)) }
  finally{ loading.value=false }
}

function toggleScope(scope:string):void {
  const index=form.scopes.indexOf(scope)
  if(index>=0) form.scopes.splice(index,1); else form.scopes.push(scope)
}

async function createKey():Promise<void> {
  if(!form.name.trim()||!form.scopes.length)return
  busy.value='create'
  try {
    const created=await api.post<ApiKeyItem>('/api-access/keys',{
      name:form.name.trim(),
      scopes:[...form.scopes],
      expires_at:form.expires_at ? new Date(form.expires_at).toISOString() : null
    })
    createdToken.value=created.token||''
    copied.value=false
    formOpen.value=false
    toasts.success('Chave criada','Copie o segredo agora; ele não será exibido novamente.')
    await load()
  } catch(error){toasts.error('Não foi possível criar a chave',errorMessage(error))}
  finally{busy.value=''}
}

async function copyText(value:string,label='Conteúdo'):Promise<void> {
  try { await navigator.clipboard.writeText(value); toasts.success(`${label} copiado`) }
  catch { toasts.error('Não foi possível copiar automaticamente') }
}

async function copyToken():Promise<void> {
  if(!createdToken.value)return
  await copyText(createdToken.value,'Chave')
  copied.value=true
}

async function revoke(key:ApiKeyItem):Promise<void> {
  if(!confirm(`Revogar a chave ${key.name}? A integração perderá acesso imediatamente.`))return
  busy.value=key.id
  try{await api.delete(`/api-access/keys/${key.id}`);toasts.success('Chave revogada');await load()}
  catch(error){toasts.error('Falha ao revogar',errorMessage(error))}
  finally{busy.value=''}
}

onMounted(load)
</script>

<template>
  <div class="page-stack api-page">
    <section class="hero-panel api-hero">
      <div>
        <span class="eyebrow">API & INTEGRAÇÕES</span>
        <h2>Integrações externas com controle real</h2>
        <p>Crie credenciais independentes do login e do token GitHub, limite cada integração por escopo e acompanhe uso, expiração e revogação em uma interface única.</p>
        <div class="button-row hero-actions">
          <button class="button primary" @click="formOpen=!formOpen"><KeyRound :size="16"/>Nova chave</button>
          <a class="button secondary" :href="docsUrl" target="_blank" rel="noreferrer"><ExternalLink :size="16"/>OpenAPI</a>
          <button class="button ghost" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
        </div>
      </div>
      <div class="metric-grid hero-metrics">
        <article class="metric-card"><span>Ativas</span><strong>{{enabledKeys.length}}</strong><small>{{keys.length}} cadastrada(s)</small></article>
        <article class="metric-card"><span>Já utilizadas</span><strong>{{usedKeys.length}}</strong><small>com atividade registrada</small></article>
        <article class="metric-card"><span>Escopos em uso</span><strong>{{uniqueScopes}}</strong><small>permissões distintas</small></article>
        <article class="metric-card"><span>Endpoint</span><strong class="endpoint-metric">v1</strong><small>API externa estável</small></article>
      </div>
    </section>

    <section class="panel endpoint-panel">
      <header><div><strong>Endpoint externo</strong><span>Use somente esta base nas aplicações integradas. A API interna continua reservada à interface autenticada.</span></div><span class="status-pill ok"><Activity :size="12"/>Disponível</span></header>
      <div class="endpoint-row"><code>{{externalBase}}</code><button class="button secondary compact" @click="copyText(externalBase,'Endpoint')"><Copy :size="14"/>Copiar</button></div>
    </section>

    <section v-if="formOpen" class="panel create-key-panel">
      <header><div><strong>Nova credencial</strong><span>Dê um nome que identifique o sistema consumidor e conceda somente o necessário.</span></div><ShieldCheck :size="20"/></header>
      <div class="form-grid">
        <label class="field"><span>Nome da integração</span><input v-model="form.name" maxlength="160" placeholder="Ex.: ERP produção"/></label>
        <label class="field"><span>Expiração opcional</span><input v-model="form.expires_at" type="datetime-local"/></label>
      </div>
      <div class="scope-grid">
        <button v-for="item in scopes" :key="item.scope" type="button" class="scope-card" :class="{active:form.scopes.includes(item.scope)}" @click="toggleScope(item.scope)">
          <span class="scope-check"><Check v-if="form.scopes.includes(item.scope)" :size="14"/></span>
          <div><strong>{{item.scope}}</strong><small>{{item.description}}</small></div>
        </button>
      </div>
      <div class="button-row"><button class="button primary" :disabled="busy==='create'||!form.name.trim()||!form.scopes.length" @click="createKey"><KeyRound :size="16"/>Gerar chave segura</button><button class="button ghost" @click="formOpen=false">Cancelar</button></div>
    </section>

    <section v-if="createdToken" class="panel token-panel">
      <header><div><strong>Segredo exibido uma única vez</strong><span>Copie agora e armazene no cofre de segredos da aplicação consumidora.</span></div><ShieldCheck :size="20"/></header>
      <div class="token-box"><code>{{createdToken}}</code><button class="button primary compact" @click="copyToken"><Check v-if="copied" :size="14"/><Copy v-else :size="14"/>{{copied?'Copiada':'Copiar chave'}}</button></div>
    </section>

    <div class="pro-grid">
      <section class="panel pro-span-6">
        <header><div><strong>Teste rápido</strong><span>Consulta de saúde da API externa com X-API-Key.</span></div><Terminal :size="18"/></header>
        <pre class="code-block">{{curlExample}}</pre>
        <button class="button ghost compact" @click="copyText(curlExample,'Exemplo')"><Copy :size="14"/>Copiar exemplo</button>
      </section>
      <section class="panel pro-span-6">
        <header><div><strong>Repositórios</strong><span>Exemplo usando Bearer sem expor o token GitHub real.</span></div><Braces :size="18"/></header>
        <pre class="code-block">{{repoExample}}</pre>
        <button class="button ghost compact" @click="copyText(repoExample,'Exemplo')"><Copy :size="14"/>Copiar exemplo</button>
      </section>
    </div>

    <section class="panel integrations-guide">
      <header><div><strong>Como integrar</strong><span>Fluxo recomendado para qualquer sistema externo.</span></div><Webhook :size="20"/></header>
      <div class="guide-grid">
        <article><b>1</b><div><strong>Crie uma chave</strong><p>Nomeie pela aplicação/ambiente e limite os escopos.</p></div></article>
        <article><b>2</b><div><strong>Guarde o segredo</strong><p>O token completo só aparece no momento da criação.</p></div></article>
        <article><b>3</b><div><strong>Consuma /external/v1</strong><p>Envie X-API-Key ou Authorization Bearer em cada chamada.</p></div></article>
        <article><b>4</b><div><strong>Revogue quando quiser</strong><p>A revogação interrompe o acesso imediatamente.</p></div></article>
      </div>
    </section>

    <section class="panel table-panel desktop-table">
      <header><div><strong>Credenciais cadastradas</strong><span>{{enabledKeys.length}} ativa(s) · o segredo nunca volta nesta listagem.</span></div></header>
      <div class="table-wrap"><table><thead><tr><th>Integração</th><th>Identificador</th><th>Escopos</th><th>Último uso</th><th>Expiração</th><th>Status</th><th></th></tr></thead><tbody>
        <tr v-for="item in keys" :key="item.id"><td><strong>{{item.name}}</strong><small>Criada em {{when(item.created_at)}}</small></td><td><code>agm_{{item.prefix}}_…</code></td><td><div class="scope-list"><code v-for="scope in item.scopes" :key="scope">{{scope}}</code></div></td><td>{{when(item.last_used_at)}}</td><td>{{relativeExpiry(item.expires_at)}}</td><td><span class="status-pill" :class="item.enabled?'ok':'bad'">{{item.enabled?'Ativa':'Revogada'}}</span></td><td><button v-if="item.enabled" class="button ghost compact danger-text" :disabled="busy===item.id" @click="revoke(item)"><Trash2 :size="14"/>Revogar</button></td></tr>
        <tr v-if="!keys.length&&!loading"><td colspan="7" class="empty">Nenhuma chave externa criada.</td></tr>
      </tbody></table></div>
    </section>

    <div class="mobile-cards">
      <article v-for="item in keys" :key="item.id" class="resource-card">
        <div class="resource-card-head"><div><strong>{{item.name}}</strong><small>agm_{{item.prefix}}_… · criada em {{when(item.created_at)}}</small></div><span class="status-pill" :class="item.enabled?'ok':'bad'">{{item.enabled?'Ativa':'Revogada'}}</span></div>
        <div class="scope-list"><code v-for="scope in item.scopes" :key="scope">{{scope}}</code></div>
        <div class="mobile-meta"><span>Último uso <strong>{{when(item.last_used_at)}}</strong></span><span>Expiração <strong>{{relativeExpiry(item.expires_at)}}</strong></span></div>
        <button v-if="item.enabled" class="button ghost danger-text full" :disabled="busy===item.id" @click="revoke(item)"><Trash2 :size="14"/>Revogar chave</button>
      </article>
      <div v-if="!keys.length&&!loading" class="resource-card empty-card">Nenhuma chave externa criada.</div>
    </div>
  </div>
</template>

<style scoped>
.api-hero{align-items:center}.hero-actions{margin-top:1rem}.hero-metrics{align-self:stretch}.endpoint-metric{font-size:1.15rem!important}.endpoint-panel{display:grid;gap:.75rem}.endpoint-row{display:flex;align-items:center;gap:.65rem;min-width:0;padding:.65rem .7rem;border:1px solid var(--border-soft);border-radius:.82rem;background:var(--surface-raised)}.endpoint-row code{flex:1;min-width:0;overflow:hidden;color:var(--text-strong);font-size:.7rem;text-overflow:ellipsis;white-space:nowrap}.form-grid{display:grid;grid-template-columns:2fr 1fr;gap:.8rem;margin-top:.8rem}.scope-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem;margin:.85rem 0}.scope-card{display:flex;align-items:flex-start;gap:.6rem;padding:.75rem;text-align:left;border:1px solid var(--border);border-radius:.82rem;background:var(--surface-raised);cursor:pointer}.scope-card.active{border-color:color-mix(in srgb,var(--primary) 62%,var(--border));background:color-mix(in srgb,var(--primary) 8%,var(--surface))}.scope-check{display:grid;place-items:center;flex:none;width:1.25rem;height:1.25rem;border:1px solid var(--border);border-radius:.38rem;color:white}.scope-card.active .scope-check{border-color:var(--primary);background:var(--primary)}.scope-card div{display:grid;gap:.18rem;min-width:0}.scope-card strong{overflow-wrap:anywhere;color:var(--text-strong);font-size:.7rem}.scope-card small{color:var(--text-muted);font-size:.62rem;line-height:1.4}.token-panel{border-color:color-mix(in srgb,var(--success) 42%,var(--border))}.token-box{display:flex;align-items:center;gap:.65rem;margin-top:.7rem;padding:.72rem;border:1px dashed color-mix(in srgb,var(--success) 30%,var(--border));border-radius:.82rem;background:var(--surface-raised)}.token-box code{flex:1;min-width:0;overflow-wrap:anywhere;color:var(--text-strong);font-size:.68rem}.panel>.code-block{margin:.75rem 0 .6rem}.integrations-guide{display:grid;gap:.8rem}.guide-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem}.guide-grid article{display:flex;gap:.6rem;padding:.72rem;border:1px solid var(--border-soft);border-radius:.82rem;background:var(--surface-raised)}.guide-grid b{display:grid;place-items:center;flex:none;width:1.55rem;height:1.55rem;border-radius:.5rem;color:white;background:linear-gradient(135deg,var(--primary),var(--secondary));font-size:.66rem}.guide-grid strong{color:var(--text-strong);font-size:.7rem}.guide-grid p{margin:.14rem 0 0;color:var(--text-muted);font-size:.62rem;line-height:1.45}.scope-list{display:flex;gap:.28rem;flex-wrap:wrap}.scope-list code{padding:.18rem .34rem;border:1px solid var(--border-soft);border-radius:.38rem;background:var(--surface-raised);font-size:.6rem}.table-wrap td strong,.table-wrap td small{display:block}.table-wrap td small{margin-top:.15rem;color:var(--text-subtle);font-size:.6rem}.table-wrap td,.table-wrap th{padding:.72rem;font-size:.67rem;border-bottom:1px solid var(--border-soft);text-align:left;vertical-align:top}.table-wrap th{color:var(--text-muted);font-size:.57rem;text-transform:uppercase;letter-spacing:.06em}.empty{text-align:center;color:var(--text-muted);padding:1.5rem}.mobile-meta{display:grid;grid-template-columns:1fr 1fr;gap:.55rem}.mobile-meta span{display:grid;gap:.12rem;color:var(--text-muted);font-size:.6rem}.mobile-meta strong{color:var(--text-strong);font-size:.65rem}.empty-card{text-align:center;color:var(--text-muted)}
@media(max-width:1040px){.scope-grid{grid-template-columns:1fr 1fr}.guide-grid{grid-template-columns:1fr 1fr}}@media(max-width:720px){.form-grid{grid-template-columns:1fr}.token-box{align-items:stretch;flex-direction:column}.token-box .button{width:100%}}@media(max-width:560px){.scope-grid,.guide-grid{grid-template-columns:1fr}.mobile-meta{grid-template-columns:1fr}.endpoint-row{align-items:stretch;flex-direction:column}.endpoint-row code{white-space:normal;overflow-wrap:anywhere}.endpoint-row .button{width:100%}}
</style>
