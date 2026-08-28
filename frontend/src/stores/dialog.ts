import { defineStore } from 'pinia'
import { ref } from 'vue'

export type DialogTone = 'info' | 'success' | 'warning' | 'danger'

export interface DialogOptions {
  title: string
  message?: string
  details?: string
  tone?: DialogTone
  confirmLabel?: string
  cancelLabel?: string
  showCancel?: boolean
  promptLabel?: string
  promptPlaceholder?: string
  promptExpected?: string
  promptValue?: string
}

export interface DialogState extends Required<Pick<DialogOptions, 'title'>> {
  id: number
  message: string
  details: string
  tone: DialogTone
  confirmLabel: string
  cancelLabel: string
  showCancel: boolean
  promptLabel: string
  promptPlaceholder: string
  promptExpected: string
  promptValue: string
}

type Resolver = (value: string | boolean | null) => void

interface QueueItem {
  state: DialogState
  resolve: Resolver
}

let sequence = 0

export const useDialogStore = defineStore('dialog', () => {
  const current = ref<DialogState | null>(null)
  const queue: QueueItem[] = []
  let activeResolver: Resolver | null = null

  function next(): void {
    if (current.value || !queue.length) return
    const item = queue.shift()!
    current.value = item.state
    activeResolver = item.resolve
  }

  function open(options: DialogOptions): Promise<string | boolean | null> {
    return new Promise((resolve) => {
      queue.push({
        resolve,
        state: {
          id: ++sequence,
          title: options.title,
          message: options.message || '',
          details: options.details || '',
          tone: options.tone || 'info',
          confirmLabel: options.confirmLabel || 'OK',
          cancelLabel: options.cancelLabel || 'Cancelar',
          showCancel: options.showCancel ?? false,
          promptLabel: options.promptLabel || '',
          promptPlaceholder: options.promptPlaceholder || '',
          promptExpected: options.promptExpected || '',
          promptValue: options.promptValue || '',
        },
      })
      next()
    })
  }

  function settle(value: string | boolean | null): void {
    const resolver = activeResolver
    activeResolver = null
    current.value = null
    resolver?.(value)
    queueMicrotask(next)
  }

  function accept(promptValue = ''): void {
    if (!current.value) return
    settle(current.value.promptLabel ? promptValue : true)
  }

  function cancel(): void {
    settle(null)
  }

  async function askConfirmation(options: DialogOptions): Promise<boolean> {
    const result = await open({ ...options, showCancel: true })
    return result === true
  }

  async function askText(options: DialogOptions): Promise<string | null> {
    const result = await open({ ...options, showCancel: true })
    return typeof result === 'string' ? result : null
  }

  async function showMessage(options: DialogOptions): Promise<void> {
    await open({ ...options, showCancel: false })
  }

  return { current, open, askConfirmation, askText, showMessage, accept, cancel }
})
