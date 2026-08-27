import { createRouter, createWebHistory } from 'vue-router'
import { pinia } from '../stores'
import { useAuthStore } from '../stores/auth'
import AppShell from '../layouts/AppShell.vue'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { title: 'Entrar' } },
    {
      path: '/', component: AppShell, meta: { requiresAuth: true }, children: [
        { path: '', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { title: 'Visão geral' } },
        { path: 'repositories', name: 'repositories', component: () => import('../views/RepositoriesView.vue'), meta: { title: 'Repositórios' } },
        { path: 'repositories/blacklist', name: 'repository-blacklist', component: () => import('../views/RepositoryBlacklistView.vue'), meta: { title: 'Lista negra de repositórios' } },
        { path: 'repositories/:id', name: 'repository-detail', component: () => import('../views/RepositoryDetailView.vue'), meta: { title: 'Detalhes do repositório' } },
        { path: 'pull-requests', name: 'pull-requests', component: () => import('../views/PullRequestsView.vue'), meta: { title: 'Pull Requests' } },
        { path: 'actions', name: 'actions', component: () => import('../views/ActionsView.vue'), meta: { title: 'GitHub Actions' } },
        { path: 'releases', name: 'releases', component: () => import('../views/ReleasesView.vue'), meta: { title: 'Releases' } },
        { path: 'issues', name: 'issues', component: () => import('../views/IssuesView.vue'), meta: { title: 'Issues' } },
        { path: 'github-tools', name: 'github-tools', component: () => import('../views/GitHubToolsView.vue'), meta: { title: 'GitHub Tools' } },
        { path: 'api-access', name: 'api-access', component: () => import('../views/ApiAccessView.vue'), meta: { title: 'API & Integrações' } },
        { path: 'backup-recovery', name: 'backup-recovery', component: () => import('../views/BackupRecoveryView.vue'), meta: { title: 'Backup & Recovery' } },
        { path: 'backup-complete', name: 'backup-complete', component: () => import('../views/CompleteBackupView.vue'), meta: { title: 'Backup completo' } },
        { path: 'deployments', name: 'deployments', component: () => import('../views/DeploymentsView.vue'), meta: { title: 'Deployment Manager' } },
        { path: 'repository-clinic', name: 'repository-clinic', component: () => import('../views/RepositoryClinicView.vue'), meta: { title: 'Repository Clinic' } },
        { path: 'audit', name: 'audit', component: () => import('../views/AuditView.vue'), meta: { title: 'Auditoria' } },
        { path: 'compliance', name: 'compliance', component: () => import('../views/ComplianceView.vue'), meta: { title: 'Conformidade GitHub' } },
        { path: 'inactivity', name: 'inactivity', component: () => import('../views/InactivityPoliciesView.vue'), meta: { title: 'Automação por inatividade' } },
        { path: 'jobs', name: 'jobs', component: () => import('../views/QueueView.vue'), meta: { title: 'Fila operacional' } },
        { path: 'notifications', name: 'notifications', component: () => import('../views/NotificationsView.vue'), meta: { title: 'Notificações' } },
        { path: 'profile', name: 'profile', component: () => import('../views/ProfileView.vue'), meta: { title: 'Meu perfil' } },
        { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { title: 'Usuários e segurança', requiresSuperuser: true } },
        { path: 'logs', name: 'logs', component: () => import('../views/LogsView.vue'), meta: { title: 'Central de logs', requiresSuperuser: true } },
        { path: 'settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: 'Configurações' } }
      ]
    },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue'), meta: { title: 'Página não encontrada' } }
  ]
})

router.beforeEach(async (to) => {
  const auth = useAuthStore(pinia)
  await auth.initialize()
  if (to.meta.requiresAuth && !auth.isAuthenticated) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.name === 'login' && auth.isAuthenticated) return { name: 'dashboard' }
  if (to.meta.requiresSuperuser && !auth.user?.is_superuser) return { name: 'dashboard' }
  if (to.meta.requiresAuth && auth.user?.must_change_password && to.name !== 'settings') return { name: 'settings', query: { password: 'required' } }
  return true
})

export default router
