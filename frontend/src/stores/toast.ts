import { ref } from 'vue'
import { defineStore } from 'pinia'

export type ToastKind = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  title: string
  message?: string
}

let nextId = 1

export const useToastStore = defineStore('toast', () => {
  const items = ref<ToastItem[]>([])

  function show(kind: ToastKind, title: string, message?: string, duration = 5000): void {
    const id = nextId++
    items.value.push({ id, kind, title, message })
    window.setTimeout(() => remove(id), duration)
  }

  function remove(id: number): void {
    items.value = items.value.filter((item) => item.id !== id)
  }

  return {
    items,
    remove,
    success: (title: string, message?: string) => show('success', title, message),
    error: (title: string, message?: string) => show('error', title, message, 7000),
    warning: (title: string, message?: string) => show('warning', title, message),
    info: (title: string, message?: string) => show('info', title, message)
  }
})
