import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export function usePwaInstall() {
  const promptEvent = ref<BeforeInstallPromptEvent | null>(null)
  const isStandalone = ref(false)

  function capture(event: BeforeInstallPromptEvent): void {
    event.preventDefault()
    promptEvent.value = event
  }

  function updateStandalone(): void {
    isStandalone.value =
      window.matchMedia('(display-mode: standalone)').matches ||
      (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  }

  async function install(): Promise<boolean> {
    if (!promptEvent.value) return false
    await promptEvent.value.prompt()
    const choice = await promptEvent.value.userChoice
    if (choice.outcome === 'accepted') promptEvent.value = null
    updateStandalone()
    return choice.outcome === 'accepted'
  }

  onMounted(() => {
    updateStandalone()
    window.addEventListener('beforeinstallprompt', capture)
    window.addEventListener('appinstalled', updateStandalone)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('beforeinstallprompt', capture)
    window.removeEventListener('appinstalled', updateStandalone)
  })

  return {
    canInstall: computed(() => Boolean(promptEvent.value) && !isStandalone.value),
    isStandalone,
    install
  }
}
