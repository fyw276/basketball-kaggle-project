# 清理项目中的临时文件和缓存
# 使用方法: .\cleanup.ps1

Write-Host "开始清理项目..." -ForegroundColor Green

# 清理 Python 缓存
Write-Host "清理 Python 缓存..." -ForegroundColor Yellow
Get-ChildItem -Path . -Include __pycache__,.pytest_cache,.coverage,htmlcov -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# 清理 Flutter/Dart 缓存
Write-Host "清理 Flutter/Dart 缓存..." -ForegroundColor Yellow
if (Test-Path "mobile/.dart_tool") {
    Remove-Item -Path "mobile/.dart_tool" -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path "mobile/build") {
    Remove-Item -Path "mobile/build" -Recurse -Force -ErrorAction SilentlyContinue
}

# 清理日志文件
Write-Host "清理日志文件..." -ForegroundColor Yellow
Get-ChildItem -Path . -Include *.log -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# 清理临时文件
Write-Host "清理临时文件..." -ForegroundColor Yellow
if (Test-Path "backend/uploads") {
    Get-ChildItem -Path "backend/uploads" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-Host "清理完成！" -ForegroundColor Green
Write-Host "建议重启 VS Code 以应用更改。" -ForegroundColor Cyan
