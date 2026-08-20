param(
    [switch]$Force,
    [int]$Port = 8080
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvPath = Join-Path $Root ".env"
$CredentialsPath = Join-Path $Root "CREDENCIAIS_INICIAIS.txt"

if ((Test-Path $EnvPath) -and -not $Force) {
    Write-Host "$EnvPath já existe; nenhuma alteração realizada."
    exit 0
}

function New-RandomUrlSafe([int]$Bytes) {
    $Buffer = New-Object byte[] $Bytes
    $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Buffer) } finally { $Rng.Dispose() }
    return [Convert]::ToBase64String($Buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-FernetKey {
    $Buffer = New-Object byte[] 32
    $Rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Buffer) } finally { $Rng.Dispose() }
    return [Convert]::ToBase64String($Buffer).Replace('+', '-').Replace('/', '_')
}

$AdminPassword = New-RandomUrlSafe 18
$PostgresPassword = New-RandomUrlSafe 24
$RabbitPassword = New-RandomUrlSafe 24
$AppSecret = New-RandomUrlSafe 64
$EncryptionKey = New-FernetKey
$WebhookSecret = New-RandomUrlSafe 48
$Url = "http://localhost:$Port"

$EnvContent = @"
COMPOSE_PROJECT_NAME=argws-git-monitor
APP_NAME="ARGWS Git Monitor"
APP_VERSION=0.2.0
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO
APP_HTTP_PORT=$Port
APP_BIND_ADDRESS=0.0.0.0
PUBLIC_BASE_URL=$Url
CORS_ORIGINS=$Url,http://127.0.0.1:$Port
APP_SECRET_KEY=$AppSecret
ENCRYPTION_KEY=$EncryptionKey
INITIAL_ADMIN_NAME="Administrador ARGWS"
INITIAL_ADMIN_EMAIL=admin@argws.com.br
INITIAL_ADMIN_PASSWORD=$AdminPassword
INITIAL_ADMIN_MUST_CHANGE_PASSWORD=true
POSTGRES_DB=gitmonitor
POSTGRES_USER=gitmonitor
POSTGRES_PASSWORD=$PostgresPassword
RABBITMQ_DEFAULT_USER=gitmonitor
RABBITMQ_DEFAULT_PASS=$RabbitPassword
RABBITMQ_MANAGEMENT_PORT=15672
GITHUB_API_URL=https://api.github.com
GITHUB_WEBHOOK_SECRET=$WebhookSecret
GITHUB_REPOSITORY_LIMIT=300
GITHUB_REQUEST_TIMEOUT_SECONDS=30
GITHUB_CONCURRENCY=5
SYNC_INTERVAL_SECONDS=600
DEMO_DATA_ENABLED=true
NOTIFICATION_RETENTION_DAYS=90
API_WORKERS=2
CELERY_CONCURRENCY=2
CELERY_MAX_TASKS_PER_CHILD=100
IMAGE_TAG=local
"@

$CredentialsContent = @"
ARGWS GIT MONITOR - CREDENCIAIS INICIAIS
============================================================

Aplicação: $Url
E-mail:    admin@argws.com.br
Senha:     $AdminPassword

RabbitMQ (somente localhost): http://localhost:15672
Usuário:   gitmonitor
Senha:     $RabbitPassword

A aplicação exige a troca da senha administrativa no primeiro acesso.
Este arquivo e o .env estão ignorados pelo Git.
"@

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($EnvPath, $EnvContent, $Utf8NoBom)
[System.IO.File]::WriteAllText($CredentialsPath, $CredentialsContent, $Utf8NoBom)

Write-Host "Segredos gerados em $EnvPath" -ForegroundColor Green
Write-Host "Credenciais gravadas em $CredentialsPath" -ForegroundColor Green
