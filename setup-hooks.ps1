# Git Hooks Setup Script for Smart Outfit Assistant (PowerShell)
# Run this script from the project root directory

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Git Hooks Setup - Smart Outfit Assistant" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in a git repository
if (-not (Test-Path ".git")) {
    Write-Host "[Error] Not in a Git repository" -ForegroundColor Red
    Write-Host "        Please run this script from the project root directory" -ForegroundColor Red
    Write-Host "        Current: $PWD" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[Success] Found Git repository" -ForegroundColor Green

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[Success] $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[Error] Python is not installed" -ForegroundColor Red
    Write-Host "        Please install Python 3.11+ first" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "[Warning] Virtual environment is not activated" -ForegroundColor Yellow
    Write-Host "          Recommended: activate your venv first" -ForegroundColor Yellow
    Write-Host "          Command: .\backend\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        exit 1
    }
}

# Install pre-commit
Write-Host ""
Write-Host "[1/4] Installing pre-commit and detect-secrets..." -ForegroundColor Cyan
pip install pre-commit==4.0.1 detect-secrets==1.5.0

if ($LASTEXITCODE -ne 0) {
    Write-Host "[Error] Failed to install packages" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Install pre-commit hooks
Write-Host ""
Write-Host "[2/4] Installing Git hooks..." -ForegroundColor Cyan
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

if ($LASTEXITCODE -ne 0) {
    Write-Host "[Error] Failed to install hooks" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[Success] Git hooks installed" -ForegroundColor Green

# Initialize secrets baseline
Write-Host ""
Write-Host "[3/4] Initializing secrets detection..." -ForegroundColor Cyan
if (-not (Test-Path "backend\.secrets.baseline")) {
    detect-secrets scan | Out-File -FilePath "backend\.secrets.baseline" -Encoding UTF8
    Write-Host "[Success] Created backend\.secrets.baseline" -ForegroundColor Green
} else {
    Write-Host "[Success] backend\.secrets.baseline already exists" -ForegroundColor Green
}

# Run hooks on all files
Write-Host ""
Write-Host "[4/4] Verifying hooks installation..." -ForegroundColor Cyan
Write-Host "Running pre-commit on all files (this may take a few minutes)..." -ForegroundColor Yellow
Write-Host ""

pre-commit run --all-files

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "[Success] Git hooks setup complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Installed hooks:" -ForegroundColor Cyan
Write-Host "  - pre-commit: Runs linting, formatting, and checks on staged files"
Write-Host "  - commit-msg: Enforces conventional commit messages"
Write-Host "  - pre-push: Runs tests before pushing"
Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  - Normal commit: git commit -m 'feat: add new feature'"
Write-Host "  - Skip hooks: git commit --no-verify"
Write-Host "  - Run manually: pre-commit run --all-files"
Write-Host ""
Write-Host "Commit message format:" -ForegroundColor Cyan
Write-Host "  type(scope): description"
Write-Host ""
Write-Host "  Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert"
Write-Host "  Example: feat(api): add user authentication endpoint"
Write-Host ""
Write-Host "Documentation:" -ForegroundColor Cyan
Write-Host "  - Full guide: backend\GIT_HOOKS.md"
Write-Host "  - Commit convention: backend\COMMIT_CONVENTION.md"
Write-Host "  - Manual install: backend\MANUAL_INSTALL.md"
Write-Host ""
Read-Host "Press Enter to exit"
