<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Braces, Check, Copy, KeyRound, RefreshCw, ShieldCheck, Trash2 } from 'lucide-vue-next'
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
const form = reactive({ name:'Integração Git Monitor', scopes:['monitoring:read','repositories:read'] as string[], expires_at:'' })

const enabledKeys = computed(() => keys.value.filter((item) => item.enabled))

function errorMessage(error:unknown):string { return error instanceof ApiError ? error.message : String(error) }
function when(value:string|null):string { return value ? new Date(value).toLocaleString('pt-BR') : '—' }

async function load():Promise<void> {
  loading.value=true
  try {
    const [scopeData,keyData]=await Promise.all([
      api.get<ApiScope[]>('/api-access/scopes'),
      api.get<ApiKeyItem[]>('/api-access/keys')
    ])
    scopes.value=scopeData; keys.value=keyData
  } catch(error){ toasts.error('Falha ao carregar API',errorMessage(error)) }
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
      name:form.name.trim(),scopes:[...form.scopes],expires_at:form.expires_at ? new Date(form.expires_at).toISOString() : null
    })
    createdToken.value=created.token||''
    copied.value=false
    toasts.success('Chave criada','O segredo completo será exibido uma única vez. Copie-o agora.')
    await load()
  } catch(error){toasts.error('Não foi possível criar a chave',errorMessage(error))}
  finally{busy.value=''}
}

async function copyToken():Promise<void> {
  if(!createdToken.value)return
  try { await navigator.clipboard.writeText(createdToken.value);copied.value=true;toasts.success('Chave copiada') }
  catch { toasts.error('Não foi possível copiar automaticamente') }
}

async function revoke(key:ApiKeyItem):Promise<void> {
  if(!confirm(`Revogar a chave ${key.name}? A integração que usa esta chave perderá acesso imediatamente.`))return
  busy.value=key.id
  try{await api.delete(`/api-access/keys/${key.id}`);toasts.success('Chave revogada');await load()}
  catch(error){toasts.error('Falha ao revogar',errorMessage(error))}
  finally{busy.value=''}
}

onMounted(load)
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div><span class="eyebrow">INTEGRAÇÕES SEGURAS</span><h2>API & Integrações</h2><p>Chaves independentes do login e do token GitHub, com escopos mínimos, expiração e revogação imediata.</p></div>
      <button class="button secondary" :disabled="loading" @click="load"><RefreshCw :size="16"/>Atualizar</button>
    </section>

    <section class="panel api-info">
      <Braces :size="22"/>
      <div><strong>API interna e API externa separadas</strong><p>A aplicação usa a API interna autenticada pela sessão. Integrações externas devem usar <code>X-API-Key</code> ou <code>Authorization: Bearer agm_...</code> nos endpoints <code>/api/v1/external/v1</code>.</p></div>
    </section>

    <section class="panel">
      <header><div><strong>Nova chave de API</strong><span>Selecione somente os recursos que a integração realmente precisa.</span></div></header>
      <div class="form-grid">
        <label class="field"><span>Nome</span><input v-model="form.name" maxlength="160" placeholder="Ex.: Integração ERP"/></label>
        <label class="field"><span>Expira em</span><input v-model="form.expires_at" type="datetime-local"/></label>
      </div>
      <div class="scope-grid">
        <button v-for="item in scopes" :key="item.scope" type="button" class="scope-card" :class="{active:form.scopes.includes(item.scope)}" @click="toggleScope(item.scope)">
          <span class="scope-check"><Check v-if="form.scopes.includes(item.scope)" :size="14"/></span>
          <div><strong>{{item.scope}}</strong><small>{{item.description}}</small></div>
        </button>
      </div>
      <button class="button primary" :disabled="busy==='create'||!form.name.trim()||!form.scopes.length" @click="createKey"><KeyRound :size="16"/>Gerar chave</button>
    </section>

    <section v-if="createdToken" class="panel token-panel">
      <header><div><strong>Copie agora</strong><span>O segredo completo não fica armazenado e não poderá ser exibido novamente.</span></div><ShieldCheck :size="20"/></header>
      <div class="token-box"><code>{{createdToken}}</code><button class="button secondary compact" @click="copyToken"><Check v-if="copied" :size="14"/><Copy v-else :size="14"/>{{copied?'Copiada':'Copiar'}}</button></div>
    </section>

    <section class="panel table-panel">
      <header><div><strong>Chaves cadastradas</strong><span>{{enabledKeys.length}} ativa(s) · o segredo nunca é retornado nesta lista.</span></div></header>
      <div class="table-wrap"><table><thead><tr><th>Nome</th><th>Prefixo</th><th>Escopos</th><th>Último uso</th><th>Expiração</th><th>Status</th><th></th></tr></thead><tbody>
        <tr v-for="item in keys" :key="item.id"><td><strong>{{item.name}}</strong><small>{{when(item.created_at)}}</small></td><td><code>agm_{{item.prefix}}_…</code></td><td><div class="scope-list"><code v-for="scope in item.scopes" :key="scope">{{scope}}</code></div></td><td>{{when(item.last_used_at)}}</td><td>{{when(item.expires_at)}}</td><td><span class="status" :class="item.enabled?'ok':'bad'">{{item.enabled?'ativa':'revogada'}}</span></td><td><button v-if="item.enabled" class="button ghost compact danger" :disabled="busy===item.id" @click="revoke(item)"><Trash2 :size="14"/>Revogar</button></td></tr>
        <tr v-if="!keys.length&&!loading"><td colspan="7" class="empty">Nenhuma chave externa criada.</td></tr>
      </tbody></table></div>
    </section>
  </div>
</template>

<style scoped>
.api-info{display:flex;align-items:flex-start;gap:.8rem}.api-info>svg{flex:none;color:var(--primary-strong)}.api-info strong{color:var(--text-strong)}.api-info p{margin:.25rem 0 0;color:var(--text-muted);font-size:.74rem;line-height:1.5}.api-info code,.token-box code,.scope-list code,td code{font-size:.66rem}.form-grid{display:grid;grid-template-columns:2fr 1fr;gap:.8rem}.scope-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin:.85rem 0}.scope-card{display:flex;align-items:flex-start;gap:.55rem;padding:.7rem;text-align:left;border:1px solid var(--border);border-radius:.75rem;background:var(--surface-raised);cursor:pointer}.scope-card.active{border-color:var(--primary);background:color-mix(in srgb,var(--primary) 7%,var(--surface))}.scope-check{display:grid;place-items:center;flex:none;width:1.2rem;height:1.2rem;border:1px solid var(--border);border-radius:.35rem;color:white}.scope-card.active .scope-check{border-color:var(--primary);background:var(--primary)}.scope-card div{display:grid;gap:.2rem}.scope-card strong{color:var(--text-strong);font-size:.7rem}.scope-card small{color:var(--text-muted);font-size:.62rem;line-height:1.35}.token-panel{border-color:color-mix(in srgb,var(--success) 40%,var(--border))}.token-box{display:flex;align-items:center;gap:.65rem;margin-top:.7rem;padding:.7rem;border:1px dashed var(--border);border-radius:.7rem;background:var(--surface-raised)}.token-box code{flex:1;overflow-wrap:anywhere;color:var(--text-strong)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:.7rem;text-align:left;border-bottom:1px solid var(--border-soft);font-size:.68rem;vertical-align:top}th{color:var(--text-muted);font-size:.58rem;text-transform:uppercase}td strong,td small{display:block}td small{margin-top:.18rem;color:var(--text-subtle)}.scope-list{display:flex;gap:.25rem;flex-wrap:wrap}.scope-list code{padding:.15rem .3rem;border-radius:.35rem;background:var(--surface-raised)}.status{font-size:.62rem;font-weight:800}.status.ok{color:var(--success)}.status.bad,.danger{color:var(--danger)}.empty{text-align:center;color:var(--text-muted);padding:1.5rem}
@media(max-width:900px){.scope-grid{grid-template-columns:1fr 1fr}.form-grid{grid-template-columns:1fr}}@media(max-width:560px){.scope-grid{grid-template-columns:1fr}.token-box{align-items:stretch;flex-direction:column}.token-box .button{width:100%}}
</style>
