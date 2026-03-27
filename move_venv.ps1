# 安全地移动虚拟环境到项目外
Write-Host "开始移动虚拟环境..." -ForegroundColor Green

# 创建备份目录
$backupDir = "$env:USERPROFILE\.clothing-assistant-venv-backup"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

# 移动 venv
if (Test-Path "venv") {
    Write-Host "移动根目录 venv..." -ForegroundColor Yellow
    Move-Item -Path "venv" -Destination "$backupDir\venv-root" -Force
    Write-Host "已移动到: $backupDir\venv-root" -ForegroundColor Cyan
}

if (Test-Path "backend/venv") {
    Write-Host "移动 backend/venv..." -ForegroundColor Yellow
    Move-Item -Path "backend/venv" -Destination "$backupDir\venv-backend" -Force
    Write-Host "已移动到: $backupDir\venv-backend" -ForegroundColor Cyan
}

Write-Host "`n虚拟环境已移动到: $backupDir" -ForegroundColor Green
Write-Host "如果需要恢复，可以从该目录复制回来。" -ForegroundColor Cyan
Write-Host "`n下一步：" -ForegroundColor Yellow
Write-Host "1. 重启 VS Code" -ForegroundColor White
Write-Host "2. 创建新的虚拟环境: python -m venv venv" -ForegroundColor White
Write-Host "3. 激活环境: .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "4. 安装依赖: pip install -r backend\requirements.txt" -ForegroundColor White
