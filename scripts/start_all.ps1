# RegFactory 一键启动脚本（无 Docker 模式）
# 需要先启动 PostgreSQL 和 Redis

$ErrorActionPreference = "Stop"

Write-Host "=== RegFactory 服务启动 ===" -ForegroundColor Cyan

# 检查 Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "错误: 未找到 Python" -ForegroundColor Red
    exit 1
}

$servicesDir = Join-Path $PSScriptRoot ".." "services"
Push-Location $servicesDir

Write-Host "`n[1/5] 启动 Config Service (:8003)..." -ForegroundColor Yellow
Start-Process python -ArgumentList "-m", "uvicorn", "config_service.main:app", "--port", "8003", "--reload" -WindowStyle Minimized

Write-Host "[2/5] 启动 SMS Service (:8001)..." -ForegroundColor Yellow
Start-Process python -ArgumentList "-m", "uvicorn", "sms_service.main:app", "--port", "8001", "--reload" -WindowStyle Minimized

Write-Host "[3/5] 启动 Account Service (:8002)..." -ForegroundColor Yellow
Start-Process python -ArgumentList "-m", "uvicorn", "account_service.main:app", "--port", "8002", "--reload" -WindowStyle Minimized

Write-Host "[4/5] 启动 Gateway (:8000)..." -ForegroundColor Yellow
Start-Process python -ArgumentList "-m", "uvicorn", "gateway.main:app", "--port", "8000", "--reload" -WindowStyle Minimized

Pop-Location

Write-Host "[5/5] 启动 Frontend (:3000)..." -ForegroundColor Yellow
$frontendDir = Join-Path $PSScriptRoot ".." "frontend"
Push-Location $frontendDir
Start-Process npm -ArgumentList "run", "dev" -WindowStyle Minimized
Pop-Location

Write-Host "`n=== 所有服务已启动 ===" -ForegroundColor Green
Write-Host "  Gateway:   http://localhost:8000" -ForegroundColor White
Write-Host "  SMS:       http://localhost:8001" -ForegroundColor White
Write-Host "  Account:   http://localhost:8002" -ForegroundColor White
Write-Host "  Config:    http://localhost:8003" -ForegroundColor White
Write-Host "  Frontend:  http://localhost:3000" -ForegroundColor White
Write-Host "  Swagger:   http://localhost:8000/docs" -ForegroundColor White
