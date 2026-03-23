# 重启后端服务脚本

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  重启后端服务" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# 步骤 1: 停止现有的 Python 进程
Write-Host "步骤 1: 停止现有的后端进程..." -ForegroundColor Yellow

$processes = Get-Process | Where-Object {
    $_.ProcessName -like "*python*" -and
    $_.Path -like "*clothing-assistant*"
}

if ($processes) {
    Write-Host "找到 $($processes.Count) 个进程，正在停止..." -ForegroundColor Yellow
    $processes | ForEach-Object {
        Write-Host "  - 停止进程 ID: $($_.Id)" -ForegroundColor Gray
        Stop-Process -Id $_.Id -Force
    }
    Start-Sleep -Seconds 2
    Write-Host "✓ 所有进程已停止" -ForegroundColor Green
} else {
    Write-Host "✓ 没有找到运行中的进程" -ForegroundColor Green
}

# 步骤 2: 启动后端服务
Write-Host "`n步骤 2: 启动后端服务..." -ForegroundColor Yellow
Write-Host "运行命令: python run.py" -ForegroundColor Gray
Write-Host ""

# 启动后端服务
python run.py
