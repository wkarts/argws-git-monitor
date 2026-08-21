import { ref } from 'vue'
import { defineStore } from 'pinia'

export type ThemePreference = 'dark' | 'light' | 'system'
const STORAGE_KEY = 'argws-git-monitor.theme'

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>('light')

  function resolvedTheme(): 'dark' | 'light' {
    if (preference.value !== 'system') return preference.value
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  function apply(): void {
    document.documentElement.dataset.theme = resolvedTheme()
  }

  function initialize(): void {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemePreference | null
    preference.value = saved && ['dark', 'light', 'system'].includes(saved) ? saved : 'light'
    apply()
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (preference.value === 'system') apply()
    })
  }

  function setPreference(value: ThemePreference): void {
    preference.value = value
    localStorage.setItem(STORAGE_KEY, value)
    apply()
  }

  return { preference, initialize, setPreference }
})
