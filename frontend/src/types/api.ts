export type HealthStatus = 'healthy' | 'running' | 'attention' | 'failing' | 'unknown'
export type ConnectionStatus = 'active' | 'error' | 'revoked' | 'demo'
export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error'
export type SyncJobStatus = 'queued' | 'running' | 'success' | 'failed' | 'cancelled'

export interface User {
  id: string
  name: string
  email: string
  is_active: boolean
  is_superuser: boolean
  must_change_password: boolean
  totp_enabled: boolean
  totp_confirmed_at: string | null
  last_login_at: string | null
  created_at: string
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  access_expires_at: string
  refresh_expires_at: string
  user: User
}

export interface AuthSession {
  accessToken: string
  refreshToken: string
  accessExpiresAt: string
  refreshExpiresAt: string
  user: User
}

export interface SessionItem {
  id: string
  expires_at: string
  revoked_at: string | null
  user_agent: string | null
  ip_address: string | null
  created_at: string
}

export interface TwoFactorStatus {
  enabled: boolean
  confirmed_at: string | null
  recovery_codes_remaining: number
}

export interface TwoFactorSetup {
  secret: string
  otpauth_uri: string
  qr_data_uri: string
  recovery_codes: string[]
}

export interface WorkflowRun {
  id: string
  github_id: number
  name: string
  display_title: string | null
  event: string | null
  status: string
  conclusion: string | null
  head_branch: string | null
  head_sha: string | null
  run_number: number | null
  run_attempt: number | null
  html_url: string
  actor_login: string | null
  github_created_at: string | null
  github_updated_at: string | null
  run_started_at: string | null
  duration_seconds: number | null
}

export interface PullRequest {
  id: string
  github_id: number
  number: number
  title: string
  state: string
  draft: boolean
  html_url: string
  user_login: string | null
  head_ref: string | null
  base_ref: string | null
  mergeable_state: string | null
  github_created_at: string | null
  github_updated_at: string | null
  closed_at: string | null
  merged_at: string | null
}

export interface Release {
  id: string
  github_id: number
  tag_name: string
  name: string | null
  draft: boolean
  prerelease: boolean
  html_url: string
  target_commitish: string | null
  github_created_at: string | null
  published_at: string | null
}

export interface HealthComponent {
  label: string
  weight: number
  points: number
  evaluated: boolean
  detail: string
}

export interface Repository {
  id: string
  connection_id: string
  github_id: number
  owner: string
  name: string
  full_name: string
  html_url: string
  description: string | null
  private: boolean
  fork: boolean
  archived: boolean
  disabled: boolean
  visibility: string
  default_branch: string
  language: string | null
  stargazers_count: number
  forks_count: number
  open_issue_count: number
  open_pr_count: number
  branch_count: number
  pushed_at: string | null
  latest_commit_sha: string | null
  latest_commit_message: string | null
  latest_commit_author: string | null
  latest_commit_at: string | null
  latest_release_tag: string | null
  latest_release_name: string | null
  latest_release_at: string | null
  latest_workflow_id: number | null
  latest_workflow_name: string | null
  latest_workflow_status: string | null
  latest_workflow_conclusion: string | null
  latest_workflow_url: string | null
  latest_workflow_at: string | null
  health_score: number
  health_status: HealthStatus
  health_coverage: number
  health_reasons: string[]
  health_components: Record<string, HealthComponent>
  monitoring_enabled: boolean
  last_synced_at: string | null
  sync_error: string | null
}

export interface RepositoryDetail extends Repository {
  workflow_runs: WorkflowRun[]
  pull_requests: PullRequest[]
  releases: Release[]
}

export interface NotificationItem {
  id: string
  repository_id: string | null
  event_type: string
  severity: NotificationSeverity
  title: string
  message: string
  url: string | null
  payload: Record<string, unknown>
  read_at: string | null
  created_at: string
}

export interface DashboardStats {
  total_repositories: number
  private_repositories: number
  public_repositories: number
  healthy: number
  running: number
  attention: number
  failing: number
  unknown: number
  health_evaluated: number
  health_pending: number
  average_health_score: number
  average_health_coverage: number
  open_pull_requests: number
  open_issues: number
  unread_notifications: number
}

export interface DashboardWorkflow extends WorkflowRun {
  repository_id: string
  repository_full_name: string
}

export interface DashboardData {
  stats: DashboardStats
  repositories: Repository[]
  recent_workflows: DashboardWorkflow[]
  recent_notifications: NotificationItem[]
}

export interface GitHubConnection {
  id: string
  name: string
  github_login: string
  github_user_id: number | null
  token_last_four: string | null
  status: ConnectionStatus
  auto_import: boolean
  api_url: string
  last_sync_at: string | null
  last_error: string | null
  rate_limit_remaining: number | null
  rate_limit_reset_at: string | null
  created_at: string
  repository_count: number
  available_repository_count: number
  oauth_scopes: string[]
}

export interface RemoteRepository {
  github_id: number
  owner: string
  name: string
  full_name: string
  html_url: string
  description: string | null
  private: boolean
  archived: boolean
  default_branch: string
  language: string | null
  selected: boolean
  permissions: Record<string, boolean>
}

export interface RepositoryImportResponse {
  message: string
  imported_count: number
  already_monitored_count: number
  queued_count: number
  repository_ids: string[]
  job_ids: string[]
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface MessageResponse { message: string }
export interface SyncResponse { message: string; task_id?: string | null; job_id?: string | null }
export interface WorkflowActionResponse { message: string; run_id: number }

export interface WebhookConfigureResult {
  repository: string
  success: boolean
  message: string
  webhook_id: number | null
}

export interface OperationWorkflow extends WorkflowRun {
  repository_id: string
  repository_full_name: string
  repository_private: boolean
}
export interface OperationPullRequest extends PullRequest {
  repository_id: string
  repository_full_name: string
  repository_private: boolean
}
export interface OperationRelease extends Release {
  repository_id: string
  repository_full_name: string
  repository_private: boolean
}
export interface IssueSummary {
  repository_id: string
  repository_full_name: string
  repository_private: boolean
  repository_html_url: string
  open_issue_count: number
  health_score: number
  health_status: HealthStatus
  last_synced_at: string | null
}

export interface SyncJob {
  id: string
  user_id: string
  connection_id: string | null
  repository_id: string | null
  celery_task_id: string | null
  kind: string
  label: string
  status: SyncJobStatus
  progress_current: number
  progress_total: number
  message: string | null
  error: string | null
  result: Record<string, unknown>
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface QueueOverview {
  queued: number
  running: number
  succeeded: number
  failed: number
  cancelled: number
  total: number
  worker_online: boolean
  worker_count: number
  workers: string[]
  worker_error: string | null
}

export interface RuntimeStatus {
  status: string
  version: string
  database: string
  redis: string
  worker_online: boolean
  worker_count: number
  workers: string[]
  queued_jobs: number
  running_jobs: number
  failed_jobs: number
  worker_error: string | null
  timestamp: string
}

export interface AdminUser {
  id: string
  name: string
  email: string
  is_active: boolean
  is_superuser: boolean
  must_change_password: boolean
  totp_enabled: boolean
  last_login_at: string | null
  created_at: string
  github_connection_count: number
  repository_count: number
  active_session_count: number
}
export interface AdminOverview {
  total_users: number
  active_users: number
  administrators: number
  two_factor_enabled: number
  active_sessions: number
}
export interface AdminPasswordResetResponse { message: string; temporary_password: string }

export interface GitHubTreeItem {
  path: string
  type: string
  mode: string
  sha: string
  size: number | null
}
export interface PackageVersion {
  id: number
  name: string
  url: string | null
  created_at: string | null
  updated_at: string | null
  tags: string[]
}
export interface ToolResult {
  message: string
  data: Record<string, unknown>
}
