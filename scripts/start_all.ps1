# RegFactory 本机单体启动脚本：仅需要 Python、Node、SQLite 和 ixBrowser（真实任务时）。
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$servicesDir = Join-Path $projectRoot "services"
$frontendDir = Join-Path $projectRoot "frontend"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "未找到 Python"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "未找到 npm"
}

Push-Location $frontendDir
try {
    Write-Host "[1/3] 构建前端..." -ForegroundColor Yellow
    npm run build
} finally {
    Pop-Location
}

Push-Location $servicesDir
try {
    Write-Host "[2/3] 执行 SQLite 迁移..." -ForegroundColor Yellow
    python -m alembic upgrade head

    Write-Host "[3/3] 启动本机单体（单 worker）..." -ForegroundColor Yellow
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
} finally {
    Pop-Location
}
