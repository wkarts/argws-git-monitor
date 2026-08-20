<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Bell,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  CircleDotDashed,
  Github,
  GitPullRequest,
  LayoutDashboard,
  LogOut,
  Menu,
  MoreHorizontal,
  PlayCircle,
  Settings,
  Tag,
  X
} from 'lucide-vue-next'
import AppLogo from '../components/AppLogo.vue'
import { api } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import type { DashboardData } from '../types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toasts = useToastStore()
const sidebarCollapsed = ref(localStorage.getItem('argws.sidebar.collapsed') === 'true')
const mobileMenuOpen = ref(false)
const mobileMoreOpen = ref(false)
const userMenuOpen = ref(false)
const online = ref(navigator.onLine)
const unreadNotifications = ref(0)
const knownNotificationIds = new Set<string>()
let notificationsInitialized = false
let refreshTimer: number | undefined

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/repositories', label: 'Repositórios', icon: Github },
  { to: '/pull-requests', label: 'Pull Requests', icon: GitPullRequest },
  { to: '/actions', label: 'Actions', icon: PlayCircle },
  { to: '/releases', label: 'Releases', icon: Tag },
  { to: '/issues', label: 'Issues', icon: CircleDotDashed },
  { to: '/notifications', label: 'Alertas', icon: Bell },
  { to: '/settings', label: 'Configurações', icon: Settings }
]

const mobilePrimaryItems = [
  { to: '/', label: 'Início', icon: LayoutDashboard },
  { to: '/repositories', label: 'Repos', icon: Github },
  { to: '/actions', label: 'Actions', icon: PlayCircle },
  { to: '/notifications', label: 'Alertas', icon: Bell }
]

const pageTitle = computed(() => String(route.meta.title || 'Visão geral'))
const firstName = computed(() => auth.user?.name?.trim().split(/\s+/)[0] || 'Admin')

function routeIsActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  if (path === '/repositories') return route.path.startsWith('/repositories')
  return route.path === path || route.path.startsWith(`${path}/`)
}

function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('argws.sidebar.collapsed', String(sidebarCollapsed.value))
}

async function loadNotificationCount(): Promise<void> {
  if (!online.value) return
  try {
    const dashboard = await api.get<DashboardData>('/dashboard')
    unreadNotifications.value = dashboard.stats.unread_notifications
    if (!notificationsInitialized) {
      dashboard.recent_notifications.forEach((item) => knownNotificationIds.add(item.id))
      notificationsInitialized = true
      return
    }
    const incoming = dashboard.recent_notifications
      .filter((item) => !item.read_at && !knownNotificationIds.has(item.id))
      .reverse()
    dashboard.recent_notifications.forEach((item) => knownNotificationIds.add(item.id))
    if ('Notification' in window && Notification.permission === 'granted') {
      for (const item of incoming) {
        try {
          const notice = new Notification(item.title, {
            body: item.message,
            icon: '/pwa-192x192.png',
            tag: item.id
          })
          notice.onclick = () => {
            window.focus()
            void router.push('/notifications')
            notice.close()
          }
        } catch {
          // Alguns navegadores móveis exigem Web Push para alertas em segundo plano.
        }
      }
    }
  } catch {
    // A tela ativa exibirá o erro de comunicação quando necessário.
  }
}

async function logout(): Promise<void> {
  userMenuOpen.value = false
  mobileMoreOpen.value = false
  await auth.logout()
  await router.replace('/login')
}

function updateOnlineState(): void {
  online.value = navigator.onLine
  if (online.value) {
    toasts.success('Conexão restaurada', 'O monitor voltou a comunicar com o servidor.')
    void loadNotificationCount()
  } else {
    toasts.warning('Sem conexão', 'Dados já carregados permanecem disponíveis na interface.')
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  mobileMenuOpen.value = false
  mobileMoreOpen.value = false
  userMenuOpen.value = false
}

watch(
  () => route.fullPath,
  () => {
    mobileMenuOpen.value = false
    mobileMoreOpen.value = false
    userMenuOpen.value = false
  }
)

onMounted(() => {
  window.addEventListener('online', updateOnlineState)
  window.addEventListener('offline', updateOnlineState)
  window.addEventListener('keydown', handleKeydown)
  void loadNotificationCount()
  refreshTimer = window.setInterval(loadNotificationCount, 60000)
})

onBeforeUnmount(() => {
  window.removeEventListener('online', updateOnlineState)
  window.removeEventListener('offline', updateOnlineState)
  window.removeEventListener('keydown', handleKeydown)
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <aside class="sidebar" :class="{ open: mobileMenuOpen }">
      <div class="sidebar-brand">
        <AppLogo :compact="sidebarCollapsed" />
        <button class="sidebar-toggle desktop-only" :aria-label="sidebarCollapsed ? 'Expandir menu' : 'Recolher menu'" @click="toggleSidebar">
          <ChevronRight v-if="sidebarCollapsed" :size="16" />
          <ChevronLeft v-else :size="16" />
        </button>
        <button class="shell-icon-button mobile-only" aria-label="Fechar menu" @click="mobileMenuOpen = false"><X :size="19" /></button>
      </div>

      <nav class="sidebar-nav" aria-label="Navegação principal">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{ active: routeIsActive(item.to) }"
          :title="sidebarCollapsed ? item.label : undefined"
        >
          <component :is="item.icon" :size="19" />
          <span>{{ item.label }}</span>
          <em v-if="item.to === '/notifications' && unreadNotifications">{{ unreadNotifications > 99 ? '99+' : unreadNotifications }}</em>
        </RouterLink>
      </nav>

      <div class="sidebar-monitor" :class="{ offline: !online }">
        <div class="monitor-heading">
          <span>Monitoramento</span>
          <i />
        </div>
        <strong>{{ online ? '24/7 ativo' : 'Desconectado' }}</strong>
        <svg viewBox="0 0 180 56" fill="none" aria-hidden="true">
          <path d="M1 48C19 44 22 34 38 36c17 2 20 13 38 7 16-5 22-24 40-20 18 4 21 18 38 10 12-5 17-20 25-30" stroke="url(#monitorLineOne)" stroke-width="2.2" stroke-linecap="round" />
          <path d="M1 53c20-2 27-10 43-8 20 2 25 8 42 4 19-4 22-13 39-11 20 2 25 10 54 1" stroke="url(#monitorLineTwo)" stroke-width="1.7" stroke-linecap="round" opacity=".72" />
          <defs>
            <linearGradient id="monitorLineOne" x1="0" y1="30" x2="180" y2="30" gradientUnits="userSpaceOnUse"><stop stop-color="#2563EB" /><stop offset="1" stop-color="#8B5CF6" /></linearGradient>
            <linearGradient id="monitorLineTwo" x1="0" y1="47" x2="180" y2="47" gradientUnits="userSpaceOnUse"><stop stop-color="#22D3EE" /><stop offset="1" stop-color="#6366F1" /></linearGradient>
          </defs>
        </svg>
      </div>

      <div class="sidebar-mobile-user mobile-only">
        <div class="avatar">{{ firstName.slice(0, 1).toUpperCase() }}</div>
        <div><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span></div>
        <button class="shell-icon-button" aria-label="Sair" @click="logout"><LogOut :size="17" /></button>
      </div>
    </aside>

    <div v-if="mobileMenuOpen" class="sidebar-backdrop" @click="mobileMenuOpen = false" />

    <section class="app-body">
      <header class="topbar">
        <button class="shell-icon-button mobile-only" aria-label="Abrir menu" @click="mobileMenuOpen = true"><Menu :size="21" /></button>

        <div class="desktop-page-title desktop-only">
          <span>ARGWS Git Monitor</span>
          <strong>{{ pageTitle }}</strong>
        </div>
        <strong class="mobile-title mobile-only">Git Monitor</strong>

        <div class="topbar-actions">
          <a class="shell-icon-button desktop-only" href="https://github.com" target="_blank" rel="noopener noreferrer" title="Abrir GitHub"><Github :size="20" /></a>
          <RouterLink to="/notifications" class="shell-icon-button notification-button" title="Notificações">
            <Bell :size="19" />
            <em v-if="unreadNotifications">{{ unreadNotifications > 9 ? '9+' : unreadNotifications }}</em>
          </RouterLink>

          <div class="user-menu-wrap desktop-only">
            <button class="user-menu-trigger" :aria-expanded="userMenuOpen" @click="userMenuOpen = !userMenuOpen">
              <span class="avatar">{{ firstName.slice(0, 1).toUpperCase() }}</span>
              <span>Olá, {{ firstName }}</span>
              <ChevronDown :size="15" />
            </button>
            <div v-if="userMenuOpen" class="user-menu-popover">
              <div class="user-menu-identity"><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span></div>
              <RouterLink to="/settings"><Settings :size="16" />Configurações</RouterLink>
              <button @click="logout"><LogOut :size="16" />Sair da conta</button>
            </div>
          </div>
        </div>
      </header>

      <div v-if="auth.user?.must_change_password" class="security-banner">
        <strong>Proteção da conta:</strong>
        altere a senha inicial antes de continuar usando a aplicação.
        <RouterLink to="/settings?password=required">Alterar agora</RouterLink>
      </div>

      <main class="content"><RouterView /></main>
    </section>

    <nav class="mobile-bottom-nav" aria-label="Navegação móvel">
      <RouterLink
        v-for="item in mobilePrimaryItems"
        :key="item.to"
        :to="item.to"
        :class="{ active: routeIsActive(item.to) }"
      >
        <span class="nav-icon-wrap">
          <component :is="item.icon" :size="20" />
          <em v-if="item.to === '/notifications' && unreadNotifications" />
        </span>
        <small>{{ item.label }}</small>
      </RouterLink>
      <button :class="{ active: mobileMoreOpen }" @click="mobileMoreOpen = true">
        <MoreHorizontal :size="21" />
        <small>Mais</small>
      </button>
    </nav>

    <div v-if="mobileMoreOpen" class="mobile-more-backdrop" @click="mobileMoreOpen = false" />
    <section v-if="mobileMoreOpen" class="mobile-more-sheet" aria-label="Mais opções">
      <header><strong>Mais opções</strong><button class="shell-icon-button" aria-label="Fechar" @click="mobileMoreOpen = false"><X :size="18" /></button></header>
      <nav>
        <RouterLink to="/pull-requests"><GitPullRequest :size="19" /><span>Pull Requests</span><ChevronRight :size="16" /></RouterLink>
        <RouterLink to="/releases"><Tag :size="19" /><span>Releases</span><ChevronRight :size="16" /></RouterLink>
        <RouterLink to="/issues"><CircleDot :size="19" /><span>Issues</span><ChevronRight :size="16" /></RouterLink>
        <RouterLink to="/settings"><Settings :size="19" /><span>Configurações</span><ChevronRight :size="16" /></RouterLink>
        <button @click="logout"><LogOut :size="19" /><span>Sair da conta</span><ChevronRight :size="16" /></button>
      </nav>
    </section>
  </div>
</template>

<style scoped>
.app-shell { min-height: 100dvh; background: var(--background); }
.sidebar {
  position: fixed;
  z-index: 1100;
  inset: 0 auto 0 0;
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
  padding: 0.9rem 0.75rem;
  border-right: 1px solid var(--border);
  background:
    radial-gradient(circle at 50% 0, color-mix(in srgb, var(--primary) 7%, transparent), transparent 26%),
    color-mix(in srgb, var(--surface) 97%, transparent);
  backdrop-filter: blur(22px);
  transition: width 0.2s ease, transform 0.25s ease;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 3.55rem;
  padding: 0 0.35rem 0.75rem;
  border-bottom: 1px solid var(--border-soft);
}
.sidebar-toggle {
  display: grid;
  place-items: center;
  width: 1.7rem;
  height: 1.7rem;
  color: var(--text-subtle);
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface-raised);
  cursor: pointer;
}
.sidebar-nav {
  display: grid;
  gap: 0.28rem;
  margin-top: 0.85rem;
}
.sidebar-nav a {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.78rem;
  min-height: 2.72rem;
  padding: 0.67rem 0.78rem;
  color: var(--text-muted);
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: 0.64rem;
  font-size: 0.79rem;
  font-weight: 650;
  transition: 0.16s ease;
}
.sidebar-nav a:hover { color: var(--text); background: color-mix(in srgb, var(--surface-raised) 85%, transparent); }
.sidebar-nav a.active {
  color: #f8fbff;
  border-color: color-mix(in srgb, var(--primary) 48%, var(--border));
  background: linear-gradient(135deg, color-mix(in srgb, var(--primary) 88%, #1d4ed8), color-mix(in srgb, var(--primary) 60%, var(--secondary)));
  box-shadow: 0 7px 20px color-mix(in srgb, var(--primary) 22%, transparent), inset 0 1px rgba(255,255,255,.13);
}
.sidebar-nav em {
  margin-left: auto;
  min-width: 1.35rem;
  padding: 0.1rem 0.28rem;
  color: white;
  text-align: center;
  font-size: 0.59rem;
  font-style: normal;
  border-radius: 999px;
  background: var(--danger);
}
.sidebar-monitor {
  margin-top: auto;
  padding: 0.78rem;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 0.8rem;
  background: linear-gradient(145deg, var(--surface-raised), color-mix(in srgb, var(--surface) 92%, var(--primary)));
}
.monitor-heading { display: flex; align-items: center; justify-content: space-between; }
.monitor-heading span { color: var(--text-muted); font-size: 0.66rem; font-weight: 700; }
.monitor-heading i { width: 0.48rem; height: 0.48rem; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); }
.sidebar-monitor.offline .monitor-heading i { background: var(--warning); box-shadow: 0 0 10px var(--warning); }
.sidebar-monitor strong { display: block; margin-top: 0.16rem; color: var(--text-strong); font-size: 0.73rem; }
.sidebar-monitor svg { width: 100%; margin-top: 0.35rem; }
.sidebar-mobile-user { grid-template-columns: auto 1fr auto; align-items: center; gap: 0.65rem; margin-top: 0.65rem; padding: 0.72rem 0.35rem 0; border-top: 1px solid var(--border-soft); }
.sidebar-mobile-user > div:nth-child(2) { display: grid; min-width: 0; }
.sidebar-mobile-user strong,.sidebar-mobile-user span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-mobile-user strong { color: var(--text); font-size: 0.72rem; }
.sidebar-mobile-user span { color: var(--text-subtle); font-size: 0.61rem; }
.avatar { display: grid; place-items: center; width: 2.05rem; height: 2.05rem; color: white; font-size: 0.76rem; font-weight: 800; border: 1px solid color-mix(in srgb, var(--primary) 45%, #fff); border-radius: 50%; background: linear-gradient(145deg, var(--primary), var(--secondary)); box-shadow: 0 0 16px color-mix(in srgb, var(--primary) 22%, transparent); }
.app-body { min-height: 100dvh; margin-left: var(--sidebar-width); transition: margin-left 0.2s ease; }
.topbar {
  position: sticky;
  z-index: 900;
  top: 0;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-height: 4.35rem;
  padding: 0.58rem clamp(1rem, 2.8vw, 1.75rem);
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--background) 89%, transparent);
  backdrop-filter: blur(20px);
}
.desktop-page-title { display: grid; flex: 1; }
.desktop-page-title span { color: var(--text-subtle); font-size: 0.61rem; letter-spacing: 0.04em; }
.desktop-page-title strong { margin-top: 0.05rem; color: var(--text-strong); font-size: 0.96rem; }
.mobile-title { flex: 1; text-align: center; color: var(--text-strong); font-size: 0.94rem; }
.topbar-actions { display: flex; align-items: center; gap: 0.48rem; margin-left: auto; }
.shell-icon-button {
  position: relative;
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 2.3rem;
  height: 2.3rem;
  padding: 0;
  color: var(--text-muted);
  text-decoration: none;
  border: 1px solid var(--border);
  border-radius: 0.68rem;
  background: var(--surface-raised);
  cursor: pointer;
  transition: 0.15s ease;
}
.shell-icon-button:hover { color: var(--text-strong); border-color: color-mix(in srgb, var(--primary) 38%, var(--border)); transform: translateY(-1px); }
.notification-button em {
  position: absolute;
  top: -0.24rem;
  right: -0.24rem;
  display: grid;
  place-items: center;
  min-width: 1rem;
  height: 1rem;
  padding: 0 0.15rem;
  color: white;
  font-size: 0.5rem;
  font-style: normal;
  font-weight: 800;
  border: 2px solid var(--background);
  border-radius: 999px;
  background: var(--secondary);
}
.user-menu-wrap { position: relative; }
.user-menu-trigger {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-height: 2.4rem;
  padding: 0.25rem 0.48rem 0.25rem 0.28rem;
  color: var(--text);
  border: 1px solid transparent;
  border-radius: 0.75rem;
  background: transparent;
  font-size: 0.72rem;
  cursor: pointer;
}
.user-menu-trigger:hover { border-color: var(--border); background: var(--surface-raised); }
.user-menu-popover {
  position: absolute;
  top: calc(100% + 0.55rem);
  right: 0;
  display: grid;
  width: 230px;
  padding: 0.5rem;
  border: 1px solid var(--border);
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--surface-raised) 97%, transparent);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(20px);
}
.user-menu-identity { display: grid; padding: 0.55rem 0.6rem 0.7rem; border-bottom: 1px solid var(--border-soft); }
.user-menu-identity strong { color: var(--text-strong); font-size: 0.75rem; }
.user-menu-identity span { overflow: hidden; color: var(--text-subtle); font-size: 0.62rem; text-overflow: ellipsis; }
.user-menu-popover a,.user-menu-popover button { display: flex; align-items: center; gap: 0.55rem; width: 100%; margin-top: 0.25rem; padding: 0.62rem; color: var(--text-muted); text-decoration: none; border: 0; border-radius: 0.58rem; background: transparent; font-size: 0.7rem; cursor: pointer; }
.user-menu-popover a:hover,.user-menu-popover button:hover { color: var(--text-strong); background: var(--surface-soft); }
.security-banner { margin: 0.8rem clamp(1rem, 3vw, 2rem) 0; padding: 0.7rem 0.9rem; color: var(--warning); font-size: 0.76rem; border: 1px solid color-mix(in srgb, var(--warning) 28%, var(--border)); border-radius: 0.75rem; background: color-mix(in srgb, var(--warning) 7%, var(--surface)); }
.security-banner a { margin-left: 0.35rem; color: var(--warning); font-weight: 750; }
.content { width: 100%; max-width: 1680px; margin: 0 auto; padding: clamp(1rem, 2.3vw, 1.8rem); padding-bottom: 2rem; }
.sidebar-is-collapsed .sidebar { width: var(--sidebar-collapsed-width); }
.sidebar-is-collapsed .app-body { margin-left: var(--sidebar-collapsed-width); }
.sidebar-is-collapsed .sidebar-brand { justify-content: center; padding-inline: 0; }
.sidebar-is-collapsed .sidebar-toggle { position: absolute; right: -0.82rem; }
.sidebar-is-collapsed .sidebar-nav a { justify-content: center; padding-inline: 0.65rem; }
.sidebar-is-collapsed .sidebar-nav a span,.sidebar-is-collapsed .sidebar-nav em { display: none; }
.sidebar-is-collapsed .sidebar-monitor { display: grid; place-items: center; min-height: 3.2rem; padding: 0.5rem; }
.sidebar-is-collapsed .sidebar-monitor > :not(.monitor-heading),.sidebar-is-collapsed .monitor-heading span { display: none; }
.sidebar-is-collapsed .monitor-heading i { width: 0.62rem; height: 0.62rem; }
.sidebar-backdrop,.mobile-bottom-nav,.mobile-more-backdrop,.mobile-more-sheet,.mobile-only { display: none; }

@media (max-width: 899px) {
  .desktop-only { display: none !important; }
  .mobile-only { display: inline-grid; }
  .sidebar { width: min(322px, 88vw); transform: translateX(-105%); box-shadow: var(--shadow-lg); }
  .sidebar.open { transform: translateX(0); }
  .sidebar-backdrop { position: fixed; z-index: 1050; inset: 0; display: block; background: rgba(0,0,0,.6); backdrop-filter: blur(2px); }
  .app-body,.sidebar-is-collapsed .app-body { margin-left: 0; }
  .topbar { min-height: 3.8rem; padding: 0.5rem 0.8rem; }
  .topbar-actions { margin-left: 0; }
  .content { padding: 0.85rem; padding-bottom: calc(6rem + env(safe-area-inset-bottom)); }
  .mobile-bottom-nav {
    position: fixed;
    z-index: 1000;
    right: 0;
    bottom: 0;
    left: 0;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    padding: 0.34rem 0.45rem max(0.34rem, env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    background: color-mix(in srgb, var(--surface) 96%, transparent);
    box-shadow: 0 -14px 32px rgba(0,0,0,.28);
    backdrop-filter: blur(20px);
  }
  .mobile-bottom-nav a,.mobile-bottom-nav button {
    display: grid;
    justify-items: center;
    gap: 0.16rem;
    min-width: 0;
    padding: 0.42rem 0.16rem;
    color: var(--text-subtle);
    text-decoration: none;
    border: 0;
    border-radius: 0.65rem;
    background: transparent;
    cursor: pointer;
  }
  .mobile-bottom-nav a.active,.mobile-bottom-nav button.active { color: var(--primary-strong); background: color-mix(in srgb, var(--primary) 10%, transparent); }
  .mobile-bottom-nav small { overflow: hidden; max-width: 100%; font-size: 0.55rem; text-overflow: ellipsis; white-space: nowrap; }
  .nav-icon-wrap { position: relative; display: grid; place-items: center; }
  .nav-icon-wrap em { position: absolute; top: -0.12rem; right: -0.28rem; width: 0.4rem; height: 0.4rem; border: 1px solid var(--surface); border-radius: 50%; background: var(--danger); }
  .mobile-more-backdrop { position: fixed; z-index: 1180; inset: 0; display: block; background: rgba(0,0,0,.62); backdrop-filter: blur(3px); }
  .mobile-more-sheet {
    position: fixed;
    z-index: 1200;
    right: 0;
    bottom: 0;
    left: 0;
    display: block;
    padding: 0.8rem 0.8rem calc(1rem + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border);
    border-radius: 1.25rem 1.25rem 0 0;
    background: var(--surface);
    box-shadow: var(--shadow-lg);
  }
  .mobile-more-sheet header { display: flex; align-items: center; justify-content: space-between; padding: 0.15rem 0.15rem 0.65rem; }
  .mobile-more-sheet header strong { color: var(--text-strong); font-size: 0.9rem; }
  .mobile-more-sheet nav { display: grid; gap: 0.22rem; }
  .mobile-more-sheet a,.mobile-more-sheet nav button { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 0.68rem; width: 100%; padding: 0.78rem; color: var(--text); text-align: left; text-decoration: none; border: 1px solid transparent; border-radius: 0.72rem; background: var(--surface-raised); font-size: 0.75rem; cursor: pointer; }
}
</style>
