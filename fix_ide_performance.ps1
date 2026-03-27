# 一键修复 IDE 性能问题
param(
    [switch]$SkipBackup,
    [switch]$DeleteOldVenv
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  IDE 性能优化脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
Write-Host "检查 Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "OK: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "错误：未找到 Python！请先安装 Python。" -ForegroundColor Red
    exit 1
}
Write-Host ""

# 备份目录
$backupDir = "$env:USERPROFILE\.clothing-assistant-venv-backup"
$newVenvDir = "$env:USERPROFILE\.virtualenvs\clothing-assistant"

# 步骤 1：备份/移动现有虚拟环境
if (-not $DeleteOldVenv) {
    Write-Host "步骤 1/5: 备份现有虚拟环境..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

    if (Test-Path "venv") {
        Write-Host "  移动 venv/ 到备份目录..." -ForegroundColor Gray
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Move-Item -Path "venv" -Destination "$backupDir\venv-root-$timestamp" -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path "backend/venv") {
        Write-Host "  移动 backend/venv/ 到备份目录..." -ForegroundColor Gray
        $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Move-Item -Path "backend/venv" -Destination "$backupDir\venv-backend-$timestamp" -Force -ErrorAction SilentlyContinue
    }

    Write-Host "OK: 备份完成" -ForegroundColor Green
} else {
    Write-Host "步骤 1/5: 删除现有虚拟环境..." -ForegroundColor Yellow

    if (Test-Path "venv") {
        Write-Host "  删除 venv/..." -ForegroundColor Gray
        Remove-Item -Path "venv" -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (Test-Path "backend/venv") {
        Write-Host "  删除 backend/venv/..." -ForegroundColor Gray
        Remove-Item -Path "backend/venv" -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Host "OK: 删除完成" -ForegroundColor Green
}
Write-Host ""

# 步骤 2：清理缓存
Write-Host "步骤 2/5: 清理缓存文件..." -ForegroundColor Yellow
Get-ChildItem -Path . -Include __pycache__,.pytest_cache,.coverage,htmlcov,*.log -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path "mobile/.dart_tool") {
    Remove-Item -Path "mobile/.dart_tool" -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "OK: 缓存清理完成" -ForegroundColor Green
Write-Host ""

# 步骤 3：创建新的虚拟环境（在项目外）
Write-Host "步骤 3/5: 创建新的虚拟环境..." -ForegroundColor Yellow
Write-Host "  位置: $newVenvDir" -ForegroundColor Gray
$venvParent = Split-Path $newVenvDir
New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
python -m venv $newVenvDir
Write-Host "OK: 虚拟环境创建完成" -ForegroundColor Green
Write-Host ""

# 步骤 4：安装依赖
Write-Host "步骤 4/5: 安装依赖（这可能需要几分钟）..." -ForegroundColor Yellow
$activateCmd = "$newVenvDir\Scripts\Activate.ps1"
& $activateCmd
Write-Host "  升级 pip..." -ForegroundColor Gray
python -m pip install --upgrade pip --quiet
Write-Host "  安装项目依赖..." -ForegroundColor Gray
pip install -r backend/requirements.txt --quiet
Write-Host "OK: 依赖安装完成" -ForegroundColor Green
Write-Host ""

# 步骤 5：创建激活脚本
Write-Host "步骤 5/5: 创建快捷激活脚本..." -ForegroundColor Yellow

$activateScriptContent = @"
# 激活虚拟环境快捷脚本
`$venvPath = "$newVenvDir\Scripts\Activate.ps1"
& `$venvPath
Write-Host "虚拟环境已激活: $newVenvDir" -ForegroundColor Green
"@

$activateScriptPath = "activate.ps1"
Set-Content -Path $activateScriptPath -Value $activateScriptContent
Write-Host "OK: 已创建 activate.ps1" -ForegroundColor Green
Write-Host ""

# 完成
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  OK: 优化完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作：" -ForegroundColor Yellow
Write-Host "1. 完全关闭 VS Code" -ForegroundColor White
Write-Host "2. 重新打开项目" -ForegroundColor White
Write-Host "3. 使用 .\activate.ps1 激活虚拟环境" -ForegroundColor White
Write-Host ""
Write-Host "虚拟环境位置: $newVenvDir" -ForegroundColor Cyan
if (-not $DeleteOldVenv) {
    Write-Host "备份位置: $backupDir" -ForegroundColor Cyan
}
Write-Host ""

# 显示文件统计
Write-Host "项目文件统计：" -ForegroundColor Yellow
$fileCount = (Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "  文件数: $fileCount" -ForegroundColor White
Write-Host ""
Write-Host "请重启 VS Code！" -ForegroundColor Green
