param(
    [string]$Repository = "wkarts/argws-git-monitor",
    [ValidateSet("private", "public", "internal")][string]$Visibility = "private"
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git não encontrado." }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "GitHub CLI (gh) não encontrado." }
& gh auth status *> $null
if ($LASTEXITCODE -ne 0) { throw "Execute 'gh auth login' antes desta publicação." }
if (-not (Test-Path .git)) { & git init -b main }
& git check-ignore -q .env
if ($LASTEXITCODE -ne 0) { throw ".env não está protegido pelo .gitignore." }
& git check-ignore -q CREDENCIAIS_INICIAIS.txt
if ($LASTEXITCODE -ne 0) { throw "Credenciais não estão protegidas pelo .gitignore." }
& git config user.name *> $null
if ($LASTEXITCODE -ne 0) { & git config user.name "wkarts" }
& git config user.email *> $null
if ($LASTEXITCODE -ne 0) { & git config user.email "wkarts@users.noreply.github.com" }
& git add .
& git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { & git commit -m "feat: entrega inicial completa do ARGWS Git Monitor" }
& gh repo view $Repository *> $null
if ($LASTEXITCODE -eq 0) {
    $ExpectedRemote = "https://github.com/$Repository.git"
    & git remote get-url origin *> $null
    if ($LASTEXITCODE -eq 0) {
        & git remote set-url origin $ExpectedRemote
    } else {
        & git remote add origin $ExpectedRemote
    }
    & git push -u origin main
} else {
    & gh repo create $Repository "--$Visibility" --source=. --remote=origin --push --description "PWA Docker para monitoramento operacional de repositórios GitHub"
}
Write-Host "Publicado em https://github.com/$Repository" -ForegroundColor Green
