@echo off
chcp 65001 >nul
REM Git Hooks Setup Script for Smart Outfit Assistant (Windows)
REM Run this script from the project root directory

echo ==========================================
echo Git Hooks Setup - Smart Outfit Assistant
echo ==========================================
echo.

REM Check if we're in a git repository
if not exist ".git" (
    echo [Error] Not in a Git repository
    echo        Please run this script from the project root directory
    echo        Current: %CD%
    pause
    exit /b 1
)

echo [Success] Found Git repository

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [Error] Python is not installed
    echo        Please install Python 3.11+
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [Success] Python version: %PYTHON_VERSION%

REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo [Warning] Virtual environment is not activated
    echo          Recommended: activate your venv first
    echo          Command: backend\venv\Scripts\activate
    echo.
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

REM Install pre-commit
echo.
echo [1/4] Installing pre-commit and detect-secrets...
pip install pre-commit==4.0.1 detect-secrets==1.5.0

if errorlevel 1 (
    echo [Error] Failed to install packages
    pause
    exit /b 1
)

REM Install pre-commit hooks
echo.
echo [2/4] Installing Git hooks...
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

if errorlevel 1 (
    echo [Error] Failed to install hooks
    pause
    exit /b 1
)

echo [Success] Git hooks installed

REM Initialize secrets baseline
echo.
echo [3/4] Initializing secrets detection...
if not exist ".secrets.baseline" (
    detect-secrets scan > .secrets.baseline
    echo [Success] Created .secrets.baseline
) else (
    echo [Success] .secrets.baseline already exists
)

REM Run hooks on all files
echo.
echo [4/4] Verifying hooks installation...
echo Running pre-commit on all files (this may take a few minutes)...
echo.

pre-commit run --all-files

echo.
echo ==========================================
echo [Success] Git hooks setup complete!
echo ==========================================
echo.
echo Installed hooks:
echo   - pre-commit: Runs linting, formatting, and checks on staged files
echo   - commit-msg: Enforces conventional commit messages
echo   - pre-push: Runs tests before pushing
echo.
echo Usage:
echo   - Normal commit: git commit -m "feat: add new feature"
echo   - Skip hooks: git commit --no-verify
echo   - Run manually: pre-commit run --all-files
echo.
echo Commit message format:
echo   type(scope): description
echo.
echo   Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
echo   Example: feat(api): add user authentication endpoint
echo.
echo Documentation:
echo   - Full guide: backend\GIT_HOOKS.md
echo   - Commit convention: backend\COMMIT_CONVENTION.md
echo   - Manual install: backend\MANUAL_INSTALL.md
echo.
pause
