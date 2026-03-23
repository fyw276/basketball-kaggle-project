@echo off
REM 快速测试后端配置脚本
REM 这个脚本会运行所有关键验证测试

echo ========================================
echo 智能穿搭助手 - 后端配置快速测试
echo ========================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\activate.bat" (
    echo [错误] 虚拟环境不存在！
    echo 请先运行: python -m venv venv
    pause
    exit /b 1
)

REM 激活虚拟环境
echo [1/6] 激活虚拟环境...
call venv\Scripts\activate.bat
echo ✓ 虚拟环境已激活
echo.

REM 检查 Python 版本
echo [2/6] 检查 Python 版本...
python --version
echo.

REM 测试基础设施
echo [3/6] 测试基础设施（数据库、Redis、模型）...
python scripts/verify_infrastructure.py
if errorlevel 1 (
    echo.
    echo [警告] 基础设施验证失败
    echo 请检查：
    echo   - PostgreSQL 是否运行
    echo   - Redis 是否运行
    echo   - .env 文件是否配置正确
    echo.
    echo 继续测试其他功能...
    echo.
)

REM 测试后端完整性
echo [4/6] 测试后端服务完整性...
python scripts/verify_backend_completion.py
if errorlevel 1 (
    echo.
    echo [警告] 后端完整性验证失败
    echo.
)

REM 运行单元测试
echo [5/6] 运行单元测试...
pytest tests/ -v --tb=short
if errorlevel 1 (
    echo.
    echo [警告] 部分单元测试失败
    echo.
)

REM 测试 API 端点（需要服务器运行）
echo [6/6] 检查 API 端点配置...
python -c "from app.main import app; routes = [f'{m} {r.path}' for r in app.routes if hasattr(r, 'methods') for m in r.methods if m != 'HEAD']; print(f'✓ 已配置 {len(routes)} 个 API 端点'); [print(f'  - {r}') for r in sorted(routes)[:10]]"
echo.

echo ========================================
echo 测试完成！
echo ========================================
echo.
echo 下一步：
echo 1. 启动后端服务: python run.py
echo 2. 访问 API 文档: http://localhost:8000/docs
echo 3. 查看详细测试指南: TESTING_GUIDE.md
echo.

pause
