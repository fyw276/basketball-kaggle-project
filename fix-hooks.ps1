# Fix Pre-commit Hooks - Clear cache and reinstall

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Fixing Pre-commit Hooks" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
$pythonVersion = python --version 2>&1
Write-Host "[Info] Detected: $pythonVersion" -ForegroundColor Yellow
Write-Host "[Info] Mypy has been removed from pre-commit hooks to avoid dependency issues" -ForegroundColor Yellow
Write-Host "[Info] You can still run mypy manually: mypy backend/app" -ForegroundColor Yellow
Write-Host ""

# Clean pre-commit cache
Write-Host "[1/5] Cleaning pre-commit cache..." -ForegroundColor Cyan
try {
    pre-commit clean
    pre-commit gc
    Write-Host "[Success] Cache cleaned" -ForegroundColor Green
} catch {
    Write-Host "[Warning] Could not clean cache (this is OK)" -ForegroundColor Yellow
}

# Delete cache directory completely
Write-Host ""
Write-Host "[2/5] Removing cache directory..." -ForegroundColor Cyan
$cachePath = "$env:USERPROFILE\.cache\pre-commit"
if (Test-Path $cachePath) {
    try {
        Remove-Item -Recurse -Force $cachePath
        Write-Host "[Success] Cache directory removed" -ForegroundColor Green
    } catch {
        Write-Host "[Warning] Could not remove cache directory (this is OK)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[Info] Cache directory does not exist" -ForegroundColor Yellow
}

# Uninstall hooks
Write-Host ""
Write-Host "[3/5] Uninstalling old hooks..." -ForegroundColor Cyan
try {
    pre-commit uninstall --hook-type pre-commit 2>$null
    pre-commit uninstall --hook-type commit-msg 2>$null
    pre-commit uninstall --hook-type pre-push 2>$null
    Write-Host "[Success] Old hooks removed" -ForegroundColor Green
} catch {
    Write-Host "[Info] No hooks to uninstall" -ForegroundColor Yellow
}

# Reinstall hooks
Write-Host ""
Write-Host "[4/5] Reinstalling hooks..." -ForegroundColor Cyan
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

Write-Host "[Success] Hooks reinstalled" -ForegroundColor Green

# Run hooks
Write-Host ""
Write-Host "[5/5] Testing hooks..." -ForegroundColor Cyan
Write-Host "Running pre-commit (this may take a few minutes on first run)..." -ForegroundColor Yellow
Write-Host "Downloading and installing tools..." -ForegroundColor Yellow
Write-Host ""

$result = pre-commit run --all-files
$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "[Success] All hooks passed!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
} else {
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host "[Info] Some hooks made changes or failed" -ForegroundColor Yellow
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This is normal on first run. The hooks auto-fixed some files." -ForegroundColor Yellow
    Write-Host "Run 'git status' to see what changed." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installed hooks:" -ForegroundColor Cyan
Write-Host "  - pre-commit: Black, isort, flake8, file checks, secrets detection" -ForegroundColor White
Write-Host "  - commit-msg: Conventional commits enforcement" -ForegroundColor White
Write-Host "  - pre-push: Pytest tests" -ForegroundColor White
Write-Host ""
Write-Host "Note: Mypy type checking has been disabled in pre-commit hooks" -ForegroundColor Yellow
Write-Host "      You can still run it manually: mypy backend/app" -ForegroundColor Yellow
Write-Host ""
Write-Host "You can now use Git normally:" -ForegroundColor Cyan
Write-Host "  git add ." -ForegroundColor White
Write-Host "  git commit -m 'feat: your message'" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
