<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertTriangle, CheckCircle2, CircleAlert, Info, X } from 'lucide-vue-next'
import { useDialogStore } from '../stores/dialog'

const dialogs = useDialogStore()
const promptValue = ref('')
const promptInput = ref<HTMLInputElement | null>(null)

const icon = computed(() => {
  const tone = dialogs.current?.tone
  if (tone === 'danger') return CircleAlert
  if (tone === 'warning') return AlertTriangle
  if (tone === 'success') return CheckCircle2
  return Info
})
const confirmationReady = computed(() => {
  const current = dialogs.current
  if (!current?.promptLabel) return true
  if (!current.promptExpected) return promptValue.value.trim().length > 0
  return promptValue.value === current.promptExpected
})

watch(() => dialogs.current?.id, async () => {
  promptValue.value = dialogs.current?.promptValue || ''
  await nextTick()
  promptInput.value?.focus()
})

function accept(): void {
  if (!confirmationReady.value) return
  dialogs.accept(promptValue.value)
}

function keydown(event: KeyboardEvent): void {
  if (!dialogs.current) return
  if (event.key === 'Escape') {
    event.preventDefault()
    dialogs.cancel()
  }
  if (event.key === 'Enter' && confirmationReady.value && !event.shiftKey) {
    event.preventDefault()
    accept()
  }
}

onMounted(() => window.addEventListener('keydown', keydown))
onBeforeUnmount(() => window.removeEventListener('keydown', keydown))
</script>

<template>
  <Teleport to="body">
    <Transition name="argws-dialog">
      <div v-if="dialogs.current" class="argws-dialog-backdrop" role="presentation">
        <section
          class="argws-dialog-card"
          :class="`tone-${dialogs.current.tone}`"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="`dialog-title-${dialogs.current.id}`"
        >
          <header class="argws-dialog-header">
            <span class="argws-dialog-icon"><component :is="icon" :size="22" /></span>
            <div>
              <span class="argws-dialog-brand">ARGWS Git Monitor</span>
              <h3 :id="`dialog-title-${dialogs.current.id}`">{{ dialogs.current.title }}</h3>
            </div>
            <button class="argws-dialog-close" type="button" aria-label="Fechar" @click="dialogs.cancel"><X :size="18" /></button>
          </header>

          <div class="argws-dialog-body">
            <p v-if="dialogs.current.message">{{ dialogs.current.message }}</p>
            <pre v-if="dialogs.current.details">{{ dialogs.current.details }}</pre>
            <label v-if="dialogs.current.promptLabel" class="argws-dialog-prompt">
              <span>{{ dialogs.current.promptLabel }}</span>
              <input
                ref="promptInput"
                v-model="promptValue"
                :placeholder="dialogs.current.promptPlaceholder"
                autocomplete="off"
                spellcheck="false"
              />
              <small v-if="dialogs.current.promptExpected">
                Digite exatamente <strong>{{ dialogs.current.promptExpected }}</strong> para liberar a operação.
              </small>
            </label>
          </div>

          <footer class="argws-dialog-footer">
            <button v-if="dialogs.current.showCancel" class="dialog-button secondary" type="button" @click="dialogs.cancel">
              {{ dialogs.current.cancelLabel }}
            </button>
            <button
              class="dialog-button primary"
              :class="{ danger: dialogs.current.tone === 'danger' }"
              type="button"
              :disabled="!confirmationReady"
              @click="accept"
            >
              {{ dialogs.current.confirmLabel }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.argws-dialog-backdrop{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:1.25rem;background:color-mix(in srgb,#07101f 58%,transparent);backdrop-filter:blur(7px)}
.argws-dialog-card{width:min(520px,100%);overflow:hidden;border:1px solid color-mix(in srgb,var(--primary) 18%,var(--border));border-radius:1.25rem;background:var(--surface);box-shadow:0 28px 80px rgba(2,8,23,.28)}
.argws-dialog-header{display:grid;grid-template-columns:auto 1fr auto;align-items:start;gap:.85rem;padding:1.1rem 1.15rem .85rem;border-bottom:1px solid var(--border-soft);background:linear-gradient(135deg,color-mix(in srgb,var(--primary) 7%,var(--surface)),var(--surface))}
.argws-dialog-icon{display:grid;place-items:center;width:2.6rem;height:2.6rem;border-radius:.82rem;color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 10%,var(--surface))}
.tone-warning .argws-dialog-icon{color:var(--warning);background:color-mix(in srgb,var(--warning) 10%,var(--surface))}.tone-danger .argws-dialog-icon{color:var(--danger);background:color-mix(in srgb,var(--danger) 9%,var(--surface))}.tone-success .argws-dialog-icon{color:var(--success);background:color-mix(in srgb,var(--success) 9%,var(--surface))}
.argws-dialog-brand{display:block;margin-bottom:.12rem;color:var(--text-subtle);font-size:.62rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.argws-dialog-header h3{margin:0;color:var(--text-strong);font-size:1rem;line-height:1.3}.argws-dialog-close{display:grid;place-items:center;width:2rem;height:2rem;padding:0;color:var(--text-muted);border:0;border-radius:.6rem;background:transparent;cursor:pointer}.argws-dialog-close:hover{color:var(--text-strong);background:var(--surface-raised)}
.argws-dialog-body{display:grid;gap:.9rem;padding:1.05rem 1.15rem}.argws-dialog-body p{margin:0;color:var(--text);font-size:.83rem;line-height:1.6;white-space:pre-line}.argws-dialog-body pre{max-height:190px;margin:0;padding:.75rem;overflow:auto;color:var(--text-muted);border:1px solid var(--border-soft);border-radius:.75rem;background:var(--surface-raised);font:600 .68rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-word}.argws-dialog-prompt{display:grid;gap:.45rem}.argws-dialog-prompt>span{color:var(--text-strong);font-size:.72rem;font-weight:800}.argws-dialog-prompt input{width:100%;min-height:2.7rem;padding:0 .78rem;color:var(--text-strong);border:1px solid var(--border);border-radius:.75rem;outline:0;background:var(--surface-raised);font:700 .76rem ui-monospace,SFMono-Regular,Menlo,monospace}.argws-dialog-prompt input:focus{border-color:var(--primary);box-shadow:0 0 0 3px color-mix(in srgb,var(--primary) 13%,transparent)}.argws-dialog-prompt small{color:var(--text-muted);font-size:.64rem;line-height:1.45}.argws-dialog-prompt strong{color:var(--text-strong)}
.argws-dialog-footer{display:flex;justify-content:flex-end;gap:.55rem;padding:.85rem 1.15rem 1.1rem;border-top:1px solid var(--border-soft)}.dialog-button{min-height:2.45rem;padding:.55rem .9rem;border:1px solid var(--border);border-radius:.72rem;font:800 .72rem inherit;cursor:pointer}.dialog-button.secondary{color:var(--text);background:var(--surface-raised)}.dialog-button.primary{color:#fff;border-color:var(--primary);background:var(--primary)}.dialog-button.primary.danger{border-color:var(--danger);background:var(--danger)}.dialog-button:disabled{opacity:.45;cursor:not-allowed}
.argws-dialog-enter-active,.argws-dialog-leave-active{transition:opacity .16s ease}.argws-dialog-enter-active .argws-dialog-card,.argws-dialog-leave-active .argws-dialog-card{transition:transform .16s ease,opacity .16s ease}.argws-dialog-enter-from,.argws-dialog-leave-to{opacity:0}.argws-dialog-enter-from .argws-dialog-card,.argws-dialog-leave-to .argws-dialog-card{opacity:0;transform:translateY(8px) scale(.985)}
@media(max-width:600px){.argws-dialog-backdrop{align-items:end;padding:.65rem}.argws-dialog-card{border-radius:1rem}.argws-dialog-footer{display:grid;grid-template-columns:1fr 1fr}.argws-dialog-footer .dialog-button:only-child{grid-column:1/-1}}
</style>
