@echo off
chcp 65001 >nul
REM Git Hooks Setup Script for Smart Outfit Assistant (Windows)
REM This script installs and configures pre-commit hooks

echo ==========================================
echo Git Hooks Setup - Smart Outfit Assistant
echo ==========================================
echo.

REM Check if we're in a git repository
if not exist "..\.git" (
    echo [错误] 不在 Git 仓库中
    echo        请从项目的 backend 目录运行此脚本
    pause
    exit /b 1
)

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装
    echo        请先安装 Python 3.11+
    pause
    exit /b 1
)

REM Check Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [成功] Python 版本: %PYTHON_VERSION%

REM Check if virtual environment is activated
if "%VIRTUAL_ENV%"=="" (
    echo [警告] 虚拟环境未激活
    echo        建议先激活虚拟环境: venv\Scripts\activate
    echo.
    set /p CONTINUE="继续安装? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

REM Install pre-commit
echo.
echo [1/4] 安装 pre-commit...
pip install pre-commit==4.0.1 detect-secrets==1.5.0

REM Install pre-commit hooks
echo.
echo [2/4] 安装 Git hooks...
cd ..
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

REM Initialize secrets baseline
echo.
echo [3/4] 初始化密钥检测...
if not exist "backend\.secrets.baseline" (
    detect-secrets scan > backend\.secrets.baseline
    echo [成功] 创建 .secrets.baseline
) else (
    echo [成功] .secrets.baseline 已存在
)

REM Run hooks on all files
echo.
echo [4/4] 验证 hooks 安装...
echo 在所有文件上运行 pre-commit（可能需要一些时间）...
pre-commit run --all-files

echo.
echo ==========================================
echo [成功] Git hooks 安装成功！
echo ==========================================
echo.
echo 已安装的 hooks:
echo   • pre-commit: 在暂存文件上运行 linting、格式化和检查
echo   • commit-msg: 强制使用规范的提交消息
echo   • pre-push: 推送前运行测试
echo.
echo 使用方法:
echo   • 正常提交: git commit -m "feat: 添加新功能"
echo   • 跳过 hooks: git commit --no-verify
echo   • 手动运行: pre-commit run --all-files
echo.
echo 提交消息格式:
echo   type(scope): description
echo.
echo   类型: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
echo   示例: feat(api): 添加用户认证端点
echo.
pause
