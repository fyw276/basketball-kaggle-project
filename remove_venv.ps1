# 删除虚拟环境（会重新安装依赖）
Write-Host "警告：这将删除虚拟环境，需要重新安装依赖！" -ForegroundColor Red
Write-Host "按任意键继续，或 Ctrl+C 取消..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Write-Host "`n开始删除虚拟环境..." -ForegroundColor Green

if (Test-Path "venv") {
    Write-Host "删除根目录 venv..." -ForegroundColor Yellow
    Remove-Item -Path "venv" -Recurse -Force
    Write-Host "已删除 venv" -ForegroundColor Cyan
}

if (Test-Path "backend/venv") {
    Write-Host "删除 backend/venv..." -ForegroundColor Yellow
    Remove-Item -Path "backend/venv" -Recurse -Force
    Write-Host "已删除 backend/venv" -ForegroundColor Cyan
}

Write-Host "`n虚拟环境已删除！" -ForegroundColor Green
Write-Host "`n下一步：" -ForegroundColor Yellow
Write-Host "1. 重启 VS Code" -ForegroundColor White
Write-Host "2. 创建新的虚拟环境: python -m venv venv" -ForegroundColor White
Write-Host "3. 激活环境: .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "4. 安装依赖: pip install -r backend\requirements.txt" -ForegroundColor White
