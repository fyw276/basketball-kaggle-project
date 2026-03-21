@echo off
chcp 65001 >nul
echo ========================================
echo 智能穿搭助手 - 后端服务启动脚本
echo ========================================
echo.

REM 检查虚拟环境是否存在
if not exist "venv\Scripts\activate.bat" (
    echo [错误] 虚拟环境不存在
    echo 请先运行以下命令创建虚拟环境：
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

REM 激活虚拟环境
echo [1/2] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 启动服务器
echo [2/2] 启动 FastAPI 服务器...
echo.
python run.py

pause
