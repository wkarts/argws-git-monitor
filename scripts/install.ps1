$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Fail([string]$Message) {
    Write-Host "`n[ERRO] $Message" -ForegroundColor Red
    exit 1
}

function Info([string]$Message) {
    Write-Host "`n[ARGWS Git Monitor] $Message" -ForegroundColor Cyan
}

function Warning([string]$Message) {
    Write-Host "`n[AVISO] $Message" -ForegroundColor Yellow
}

function Get-EnvValue([string]$Name, [string]$DefaultValue = "") {
    $Pattern = "^" + [regex]::Escape($Name) + "="
    $Line = Get-Content .env | Where-Object { $_ -match $Pattern } | Select-Object -First 1
    if (-not $Line) {
        return $DefaultValue
    }

    return ($Line -replace $Pattern, "").Trim('"')
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker não encontrado. Instale o Docker Desktop com suporte ao Compose."
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "O plugin 'docker compose' não está disponível."
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "O Docker Desktop/Engine não está em execução."
}

$DataDirectories = @(
    "data-postgres",
    "data-redis",
    "data-rabbitmq",
    "data-logs\api",
    "data-logs\worker",
    "data-logs\beat",
    "data-logs\migrate",
    "data-logs\web",
    "data-logs\postgres",
    "data-logs\redis",
    "data-logs\rabbitmq"
)
foreach ($DirectoryName in $DataDirectories) {
    New-Item -ItemType Directory -Path (Join-Path $Root $DirectoryName) -Force | Out-Null
}

if (-not (Test-Path ".env")) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/generate-env.ps1
    if ($LASTEXITCODE -ne 0) {
        Fail "Não foi possível gerar o arquivo .env."
    }
}

$InstallSource = Get-EnvValue "INSTALL_SOURCE" "ghcr"
$ComposeFiles = @("-f", "compose.yaml")
if ($InstallSource -eq "ghcr") {
    $ComposeFiles += @("-f", "compose.ghcr.yaml")
}

Info "Validando a configuração Docker"
& docker compose @ComposeFiles config -q
if ($LASTEXITCODE -ne 0) {
    Fail "Configuração Docker inválida."
}

if ($InstallSource -eq "local") {
    Info "Construindo as imagens locais :latest"
    & docker compose @ComposeFiles up -d --build --force-recreate --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        Fail "Falha ao construir ou iniciar a stack."
    }
}
else {
    Info "Baixando as imagens oficiais :latest do GHCR"
    & docker compose @ComposeFiles pull

    if ($LASTEXITCODE -eq 0) {
        Info "Iniciando a stack com o digest mais recente"
        & docker compose @ComposeFiles up -d --no-build --force-recreate --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            Fail "Falha ao iniciar a stack com as imagens do GHCR."
        }
    }
    else {
        Warning "Não foi possível baixar uma ou mais imagens do GHCR. Será realizado o build local como contingência."
        $ComposeFiles = @("-f", "compose.yaml")
        & docker compose @ComposeFiles up -d --build --force-recreate --remove-orphans
        if ($LASTEXITCODE -ne 0) {
            Fail "Falha ao iniciar a stack."
        }
    }
}

$PublicUrl = Get-EnvValue "PUBLIC_BASE_URL" "http://localhost:8080"
$HttpPort = Get-EnvValue "APP_HTTP_PORT" "8080"
$HealthUrl = "http://127.0.0.1:$HttpPort/api/v1/health/ready"
$Healthy = $false

for ($i = 0; $i -lt 90; $i++) {
    try {
        $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        if ($Response.StatusCode -eq 200) {
            $Healthy = $true
            break
        }
    }
    catch {
    }

    Start-Sleep -Seconds 2
}

if (-not $Healthy) {
    & docker compose @ComposeFiles ps
    & docker compose @ComposeFiles logs --tail=120 migrate api worker web
    Fail "A verificação de saúde não foi concluída. Consulte os logs acima."
}

Info "Instalação concluída"
& docker compose @ComposeFiles ps
Write-Host "`nAplicação: $PublicUrl" -ForegroundColor Green
Write-Host "Imagens: :latest"
Write-Host "Versão: lida do próprio aplicativo"
Write-Host "Credenciais: $Root\CREDENCIAIS_INICIAIS.txt"
Write-Host "Persistência: $Root\data-postgres, $Root\data-redis, $Root\data-rabbitmq e $Root\data-logs`n"
