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

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker não encontrado. Instale o Docker Desktop com suporte ao Compose."
}
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail "O plugin 'docker compose' não está disponível." }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "O Docker Desktop/Engine não está em execução." }

if (-not (Test-Path ".env")) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/generate-env.ps1
    if ($LASTEXITCODE -ne 0) { Fail "Não foi possível gerar o arquivo .env." }
}

Info "Validando a configuração Docker"
& docker compose config -q
if ($LASTEXITCODE -ne 0) { Fail "Configuração Docker inválida." }

Info "Construindo e iniciando todos os serviços"
& docker compose up -d --build --remove-orphans
if ($LASTEXITCODE -ne 0) { Fail "Falha ao iniciar a stack." }

$PublicUrl = "http://localhost:8080"
$UrlLine = Get-Content .env | Where-Object { $_ -match '^PUBLIC_BASE_URL=' } | Select-Object -First 1
if ($UrlLine) { $PublicUrl = ($UrlLine -replace '^PUBLIC_BASE_URL=', '').Trim('"') }
$HttpPort = "8080"
$PortLine = Get-Content .env | Where-Object { $_ -match '^APP_HTTP_PORT=' } | Select-Object -First 1
if ($PortLine) { $HttpPort = ($PortLine -replace '^APP_HTTP_PORT=', '').Trim('"') }
$HealthUrl = "http://127.0.0.1:$HttpPort/api/v1/health/ready"
$Healthy = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $Response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
        if ($Response.StatusCode -eq 200) { $Healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

if (-not $Healthy) {
    & docker compose ps
    & docker compose logs --tail=120 migrate api worker web
    Fail "A verificação de saúde não foi concluída. Consulte os logs acima."
}

Info "Instalação concluída"
& docker compose ps
Write-Host "`nAplicação: $PublicUrl" -ForegroundColor Green
Write-Host "Credenciais: $Root\CREDENCIAIS_INICIAIS.txt`n"
