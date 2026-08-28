<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Activity, Bell, Braces, ChevronDown, ChevronLeft, ChevronRight, CircleDotDashed,
  ClipboardList, DatabaseBackup, FileText, Github, GitPullRequest, LayoutDashboard,
  ListChecks, LogOut, Menu, MoreHorizontal, PlayCircle, Server, Settings,
  ShieldAlert, Stethoscope, Tag, UserRound, Users, Wrench, X
} from 'lucide-vue-next'
import AppLogo from '../components/AppLogo.vue'
import { api } from '../services/api'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'
import type { DashboardData, QueueOverview } from '../types/api'

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
const queueActive = ref(0)
const knownNotificationIds = new Set<string>()
let notificationsInitialized = false
let refreshTimer: number | undefined
let realtimeRefreshTimer: number | undefined
let shellRefreshing = false

const navItems = computed(() => [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/repositories', label: 'Repositórios', icon: Github },
  { to: '/pull-requests', label: 'Pull Requests', icon: GitPullRequest },
  { to: '/actions', label: 'Actions', icon: PlayCircle },
  { to: '/releases', label: 'Releases', icon: Tag },
  { to: '/issues', label: 'Issues', icon: CircleDotDashed },
  { to: '/github-tools', label: 'GitHub Tools', icon: Wrench },
  { to: '/api-access', label: 'API & Integrações', icon: Braces },
  { to: '/backup-recovery', label: 'Backup & Recovery', icon: DatabaseBackup },
  { to: '/deployments', label: 'Deployments', icon: Server },
  { to: '/repository-clinic', label: 'Repository Clinic', icon: Stethoscope },
  { to: '/inactivity', label: 'Inatividade', icon: Activity },
  { to: '/jobs', label: 'Fila', icon: ListChecks, badge: queueActive.value },
  { to: '/notifications', label: 'Alertas', icon: Bell, badge: unreadNotifications.value },
  { to: '/compliance', label: 'Conformidade', icon: ShieldAlert },
  { to: '/audit', label: 'Auditoria', icon: ClipboardList },
  ...(auth.user?.is_superuser ? [
    { to: '/users', label: 'Usuários', icon: Users },
    { to: '/logs', label: 'Logs', icon: FileText }
  ] : []),
  { to: '/settings', label: 'Configurações', icon: Settings }
])
const mobilePrimaryItems = computed(() => [
  { to: '/', label: 'Início', icon: LayoutDashboard },
  { to: '/repositories', label: 'Repos', icon: Github },
  { to: '/actions', label: 'Actions', icon: PlayCircle },
  { to: '/jobs', label: 'Fila', icon: ListChecks, badge: queueActive.value }
])
const pageTitle = computed(() => String(route.meta.title || 'Visão geral'))
const firstName = computed(() => auth.user?.name?.trim().split(/\s+/)[0] || 'Admin')
const avatarUrl = computed(() => auth.user?.avatar_url || '')

function routeIsActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path === path || route.path.startsWith(`${path}/`)
}
function toggleSidebar(): void {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem('argws.sidebar.collapsed', String(sidebarCollapsed.value))
}

async function refreshShellData(): Promise<void> {
  if (!online.value || shellRefreshing) return
  shellRefreshing = true
  try {
    const [dashboard, queue] = await Promise.all([
      api.get<DashboardData>('/dashboard'),
      api.get<QueueOverview>('/jobs/overview')
    ])
    unreadNotifications.value = dashboard.stats.unread_notifications
    queueActive.value = queue.queued + queue.running

    if (!notificationsInitialized) {
      dashboard.recent_notifications.forEach((item) => knownNotificationIds.add(item.id))
      notificationsInitialized = true
      return
    }

    const incoming = dashboard.recent_notifications
      .filter((item) => !item.read_at && !knownNotificationIds.has(item.id))
      .reverse()
    dashboard.recent_notifications.forEach((item) => knownNotificationIds.add(item.id))

    // Push/Web Notifications continuam sendo notificações. O DialogHost é usado
    // somente para dialogs de confirmação/entrada, nunca como substituto do push.
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
          // Em background a entrega pode depender do Service Worker/Web Push.
        }
      }
    }
  } catch {
    // A página ativa apresenta o erro específico; o shell não duplica ruído.
  } finally {
    shellRefreshing = false
  }
}

function handleRealtime(event: Event): void {
  const detail = (event as CustomEvent<RealtimeEvent>).detail
  if (!detail || detail.type === 'realtime.heartbeat' || detail.type === 'realtime.connected') return
  if (!(
    detail.type.startsWith('job.')
    || detail.type.startsWith('github.')
    || detail.type.startsWith('repository.')
    || detail.type.startsWith('notification.')
    || detail.type.startsWith('backup.')
  )) return
  window.clearTimeout(realtimeRefreshTimer)
  realtimeRefreshTimer = window.setTimeout(() => void refreshShellData(), 250)
}

async function logout(): Promise<void> {
  userMenuOpen.value = false
  mobileMoreOpen.value = false
  await auth.logout()
  await router.replace('/login')
}
function updateOnlineState(): void {
  online.value = navigator.onLine
  online.value
    ? (toasts.success('Conexão restaurada'), void refreshShellData())
    : toasts.warning('Sem conexão', 'Dados já carregados permanecem disponíveis.')
}
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    mobileMenuOpen.value = false
    mobileMoreOpen.value = false
    userMenuOpen.value = false
  }
}
watch(() => route.fullPath, () => {
  mobileMenuOpen.value = false
  mobileMoreOpen.value = false
  userMenuOpen.value = false
})
onMounted(() => {
  window.addEventListener('online', updateOnlineState)
  window.addEventListener('offline', updateOnlineState)
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener(REALTIME_EVENT, handleRealtime)
  void refreshShellData()
  // WebSocket é o caminho normal. O timer é somente fallback de reconciliação.
  refreshTimer = window.setInterval(refreshShellData, 300000)
})
onBeforeUnmount(() => {
  window.removeEventListener('online', updateOnlineState)
  window.removeEventListener('offline', updateOnlineState)
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener(REALTIME_EVENT, handleRealtime)
  window.clearTimeout(realtimeRefreshTimer)
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="app-shell" :class="{ 'sidebar-is-collapsed': sidebarCollapsed }">
    <aside class="sidebar" :class="{ open: mobileMenuOpen }">
      <div class="sidebar-brand">
        <AppLogo :compact="sidebarCollapsed" />
        <button class="sidebar-toggle desktop-only" type="button" @click="toggleSidebar">
          <ChevronRight v-if="sidebarCollapsed" :size="16" /><ChevronLeft v-else :size="16" />
        </button>
        <button class="shell-icon-button mobile-only" type="button" @click="mobileMenuOpen=false"><X :size="19" /></button>
      </div>

      <nav class="sidebar-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{ active: routeIsActive(item.to) }"
          :title="sidebarCollapsed ? item.label : undefined"
        >
          <component :is="item.icon" :size="19" />
          <span>{{ item.label }}</span>
          <em v-if="item.badge">{{ item.badge > 99 ? '99+' : item.badge }}</em>
        </RouterLink>
      </nav>

      <div class="sidebar-monitor" :class="{ offline: !online }">
        <div class="monitor-heading"><span>Monitoramento</span><i /></div>
        <strong>{{ online ? 'Interface online' : 'Desconectado' }}</strong>
        <small v-if="queueActive">{{ queueActive }} job(s) ativo(s)</small>
        <small v-else>Realtime ativo; fila reservada a tarefas pesadas</small>
        <svg viewBox="0 0 180 56" fill="none" aria-hidden="true">
          <path d="M1 48C19 44 22 34 38 36c17 2 20 13 38 7 16-5 22-24 40-20 18 4 21 18 38 10 12-5 17-20 25-30" stroke="url(#shell-a)" stroke-width="2.2"/>
          <path d="M1 53c20-2 27-10 43-8 20 2 25 8 42 4 19-4 22-13 39-11 20 2 25 10 54 1" stroke="url(#shell-b)" stroke-width="1.7"/>
          <defs>
            <linearGradient id="shell-a"><stop stop-color="#2563EB"/><stop offset="1" stop-color="#8B5CF6"/></linearGradient>
            <linearGradient id="shell-b"><stop stop-color="#22D3EE"/><stop offset="1" stop-color="#6366F1"/></linearGradient>
          </defs>
        </svg>
      </div>
    </aside>
    <div v-if="mobileMenuOpen" class="sidebar-backdrop" @click="mobileMenuOpen=false" />

    <section class="app-body">
      <header class="topbar">
        <button class="shell-icon-button mobile-only" type="button" @click="mobileMenuOpen=true"><Menu :size="21" /></button>
        <div class="desktop-page-title desktop-only"><span>ARGWS Git Monitor</span><strong>{{ pageTitle }}</strong></div>
        <strong class="mobile-title mobile-only">{{ pageTitle }}</strong>
        <div class="topbar-actions">
          <a class="shell-icon-button desktop-only" href="https://github.com" target="_blank" rel="noopener"><Github :size="20" /></a>
          <RouterLink to="/notifications" class="shell-icon-button notification-button"><Bell :size="19" /><em v-if="unreadNotifications">{{ unreadNotifications > 9 ? '9+' : unreadNotifications }}</em></RouterLink>
          <div class="user-menu-wrap desktop-only">
            <button class="user-menu-trigger" type="button" @click="userMenuOpen=!userMenuOpen">
              <span class="avatar"><img v-if="avatarUrl" :src="avatarUrl" :alt="auth.user?.name || 'Usuário'" /><template v-else>{{ firstName.slice(0,1).toUpperCase() }}</template></span>
              <span>Olá, {{ firstName }}</span><ChevronDown :size="15" />
            </button>
            <div v-if="userMenuOpen" class="user-menu-popover">
              <div class="user-menu-identity"><strong>{{ auth.user?.name }}</strong><span>{{ auth.user?.email }}</span><small>{{ auth.user?.job_title || (auth.user?.is_superuser ? 'Administrador' : 'Usuário') }}</small></div>
              <RouterLink to="/profile"><UserRound :size="16" />Meu perfil</RouterLink>
              <RouterLink to="/audit"><ClipboardList :size="16" />Auditoria</RouterLink>
              <RouterLink v-if="auth.user?.is_superuser" to="/users"><Users :size="16" />Usuários</RouterLink>
              <RouterLink v-if="auth.user?.is_superuser" to="/logs"><FileText :size="16" />Central de logs</RouterLink>
              <RouterLink to="/settings"><Settings :size="16" />Configurações</RouterLink>
              <button type="button" @click="logout"><LogOut :size="16" />Sair da conta</button>
            </div>
          </div>
        </div>
      </header>

      <div v-if="auth.user?.must_change_password" class="security-banner"><strong>Proteção da conta:</strong> defina sua senha definitiva para continuar. <RouterLink to="/settings?password=required">Alterar agora</RouterLink></div>
      <main class="content"><RouterView /></main>
    </section>

    <nav class="mobile-bottom-nav">
      <RouterLink v-for="item in mobilePrimaryItems" :key="item.to" :to="item.to" :class="{ active: routeIsActive(item.to) }">
        <span class="nav-icon-wrap"><component :is="item.icon" :size="20" /><em v-if="item.badge" /></span><small>{{ item.label }}</small>
      </RouterLink>
      <button type="button" :class="{ active: mobileMoreOpen }" @click="mobileMoreOpen=true"><MoreHorizontal :size="21"/><small>Mais</small></button>
    </nav>
    <div v-if="mobileMoreOpen" class="mobile-more-backdrop" @click="mobileMoreOpen=false" />
    <section v-if="mobileMoreOpen" class="mobile-more-sheet">
      <header><strong>Mais opções</strong><button class="shell-icon-button" type="button" @click="mobileMoreOpen=false"><X :size="18"/></button></header>
      <nav>
        <RouterLink to="/pull-requests"><GitPullRequest :size="19"/><span>Pull Requests</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/releases"><Tag :size="19"/><span>Releases</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/issues"><CircleDotDashed :size="19"/><span>Issues</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/github-tools"><Wrench :size="19"/><span>GitHub Tools</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/api-access"><Braces :size="19"/><span>API & Integrações</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/backup-recovery"><DatabaseBackup :size="19"/><span>Backup & Recovery</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/backup-complete"><DatabaseBackup :size="19"/><span>Backup completo</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/deployments"><Server :size="19"/><span>Deployments</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/repository-clinic"><Stethoscope :size="19"/><span>Repository Clinic</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/compliance"><ShieldAlert :size="19"/><span>Conformidade</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/inactivity"><Activity :size="19"/><span>Inatividade</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/notifications"><Bell :size="19"/><span>Alertas</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/audit"><ClipboardList :size="19"/><span>Auditoria</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/profile"><UserRound :size="19"/><span>Meu perfil</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink v-if="auth.user?.is_superuser" to="/users"><Users :size="19"/><span>Usuários</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink v-if="auth.user?.is_superuser" to="/logs"><FileText :size="19"/><span>Logs</span><ChevronRight :size="16"/></RouterLink>
        <RouterLink to="/settings"><Settings :size="19"/><span>Configurações</span><ChevronRight :size="16"/></RouterLink>
        <button type="button" @click="logout"><LogOut :size="19"/><span>Sair</span><ChevronRight :size="16"/></button>
      </nav>
    </section>
  </div>
</template>

<style scoped>
.app-shell{min-height:100dvh;background:var(--background)}
.sidebar{position:fixed;z-index:1100;inset:0 auto 0 0;display:flex;flex-direction:column;width:var(--sidebar-width);padding:.9rem .75rem;border-right:1px solid var(--border);background:var(--surface);transition:width .2s ease,transform .25s ease}
.sidebar-brand{position:relative;display:flex;align-items:center;justify-content:space-between;min-height:3.55rem;padding:0 .35rem .75rem;border-bottom:1px solid var(--border-soft)}
.sidebar-toggle,.shell-icon-button{display:grid;place-items:center;width:2.35rem;height:2.35rem;padding:0;color:var(--text-muted);border:1px solid var(--border);border-radius:.72rem;background:var(--surface-raised);cursor:pointer}
.sidebar-toggle{width:1.7rem;height:1.7rem;border-radius:50%}
.sidebar-nav{display:grid;gap:.22rem;margin-top:.7rem;overflow-y:auto;min-height:0;padding-right:.15rem;scrollbar-width:thin}
.sidebar-nav a{position:relative;display:flex;align-items:center;gap:.72rem;min-height:2.42rem;padding:.52rem .7rem;color:var(--text-muted);text-decoration:none;border:1px solid transparent;border-radius:.64rem;font-size:.73rem;font-weight:700}
.sidebar-nav a:hover{color:var(--text-strong);background:var(--surface-raised)}
.sidebar-nav a.active{color:#fff;border-color:color-mix(in srgb,var(--primary) 48%,var(--border));background:linear-gradient(135deg,var(--primary),color-mix(in srgb,var(--primary) 66%,var(--secondary)));box-shadow:0 7px 20px color-mix(in srgb,var(--primary) 20%,transparent)}
.sidebar-nav em{margin-left:auto;min-width:1.25rem;padding:.08rem .28rem;color:#fff;text-align:center;font-size:.55rem;font-style:normal;border-radius:999px;background:var(--danger)}
.sidebar-monitor{margin-top:.6rem;padding:.65rem;border:1px solid var(--border);border-radius:.85rem;background:var(--surface-raised)}
.monitor-heading{display:flex;justify-content:space-between;color:var(--text-muted);font-size:.62rem}.monitor-heading i{width:.5rem;height:.5rem;border-radius:50%;background:var(--success);box-shadow:0 0 8px var(--success)}.sidebar-monitor.offline .monitor-heading i{background:var(--danger);box-shadow:0 0 8px var(--danger)}
.sidebar-monitor strong{display:block;color:var(--text-strong);font-size:.69rem}.sidebar-monitor small{display:block;color:var(--primary-strong);font-size:.56rem;line-height:1.35}.sidebar-monitor svg{width:100%;height:35px;margin-top:.2rem}
.app-body{min-height:100dvh;margin-left:var(--sidebar-width);transition:margin-left .2s ease}
.topbar{position:sticky;z-index:900;top:0;display:flex;align-items:center;justify-content:space-between;gap:1rem;min-height:5rem;padding:.75rem 1.75rem;border-bottom:1px solid var(--border);background:color-mix(in srgb,var(--background) 92%,transparent);backdrop-filter:blur(18px)}
.desktop-page-title{display:grid}.desktop-page-title span{color:var(--text-muted);font-size:.6rem}.desktop-page-title strong,.mobile-title{color:var(--text-strong);font-size:.83rem}
.topbar-actions{display:flex;align-items:center;gap:.45rem}.notification-button{position:relative}.notification-button em{position:absolute;top:-.25rem;right:-.25rem;display:grid;place-items:center;min-width:1.1rem;height:1.1rem;padding:0 .2rem;color:#fff;font-size:.52rem;font-style:normal;border-radius:999px;background:var(--danger)}
.user-menu-wrap{position:relative}.user-menu-trigger{display:flex;align-items:center;gap:.5rem;min-height:2.35rem;color:var(--text);border:0;background:transparent;cursor:pointer}.avatar{display:grid;place-items:center;width:2.25rem;height:2.25rem;overflow:hidden;color:#fff;border-radius:50%;background:linear-gradient(135deg,var(--primary),var(--secondary));font-weight:800}.avatar img{width:100%;height:100%;object-fit:cover}
.user-menu-popover{position:absolute;top:calc(100% + .5rem);right:0;width:255px;padding:.45rem;border:1px solid var(--border);border-radius:.8rem;background:var(--surface);box-shadow:var(--shadow-md)}.user-menu-identity{display:grid;padding:.55rem;border-bottom:1px solid var(--border-soft)}.user-menu-identity strong{color:var(--text-strong)}.user-menu-identity span,.user-menu-identity small{color:var(--text-muted);font-size:.62rem}.user-menu-popover a,.user-menu-popover button{display:flex;align-items:center;gap:.5rem;width:100%;padding:.6rem;color:var(--text);text-decoration:none;border:0;background:transparent;border-radius:.55rem;cursor:pointer}.user-menu-popover a:hover,.user-menu-popover button:hover{background:var(--surface-raised)}
.content{padding:1.6rem 1.75rem 5rem}.security-banner{padding:.55rem 1.75rem;color:var(--warning);font-size:.7rem;border-bottom:1px solid color-mix(in srgb,var(--warning) 25%,var(--border));background:color-mix(in srgb,var(--warning) 7%,var(--surface))}.security-banner a{font-weight:800}
.sidebar-is-collapsed .sidebar{width:var(--sidebar-collapsed-width)}.sidebar-is-collapsed .app-body{margin-left:var(--sidebar-collapsed-width)}.sidebar-is-collapsed .sidebar-nav a{justify-content:center}.sidebar-is-collapsed .sidebar-nav a span,.sidebar-is-collapsed .sidebar-nav em{display:none}
.mobile-bottom-nav,.mobile-more-sheet,.sidebar-backdrop,.mobile-more-backdrop,.mobile-only{display:none}
@media(max-width:820px){.desktop-only{display:none!important}.mobile-only{display:grid}.sidebar{width:min(88vw,320px);transform:translateX(-105%)}.sidebar.open{transform:translateX(0)}.app-body,.sidebar-is-collapsed .app-body{margin-left:0}.sidebar-backdrop,.mobile-more-backdrop{position:fixed;z-index:1050;inset:0;display:block;background:rgba(3,8,18,.55);backdrop-filter:blur(2px)}.topbar{min-height:4rem;padding:.65rem .85rem}.content{padding:1rem .85rem 6.5rem}.mobile-bottom-nav{position:fixed;z-index:1000;right:.6rem;bottom:.6rem;left:.6rem;display:grid;grid-template-columns:repeat(5,1fr);padding:.35rem;border:1px solid var(--border);border-radius:1rem;background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:var(--shadow-md);backdrop-filter:blur(18px)}.mobile-bottom-nav a,.mobile-bottom-nav button{display:grid;place-items:center;gap:.15rem;min-height:3.2rem;color:var(--text-muted);text-decoration:none;border:0;border-radius:.7rem;background:transparent}.mobile-bottom-nav .active{color:var(--primary-strong);background:color-mix(in srgb,var(--primary) 9%,var(--surface))}.mobile-bottom-nav small{font-size:.56rem}.nav-icon-wrap{position:relative}.nav-icon-wrap em{position:absolute;right:-.2rem;top:-.1rem;width:.4rem;height:.4rem;border-radius:50%;background:var(--danger)}.mobile-more-sheet{position:fixed;z-index:1200;right:.6rem;bottom:.6rem;left:.6rem;display:block;max-height:80dvh;overflow:auto;padding:.75rem;border:1px solid var(--border);border-radius:1rem;background:var(--surface);box-shadow:var(--shadow-lg)}.mobile-more-sheet header{display:flex;align-items:center;justify-content:space-between;padding:.2rem .25rem .6rem}.mobile-more-sheet header strong{color:var(--text-strong)}.mobile-more-sheet nav{display:grid}.mobile-more-sheet nav a,.mobile-more-sheet nav button{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.65rem;min-height:2.9rem;padding:.55rem;color:var(--text);text-decoration:none;border:0;border-top:1px solid var(--border-soft);background:transparent;text-align:left}.sidebar-brand{padding-right:.15rem}}
</style>
