@echo off
echo ========================================
echo 安装百炼 DashScope SDK
echo ========================================
echo.

pip install "dashscope>=1.20.0,<2.0.0"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo 安装成功！
    echo ========================================
    echo.
    echo 现在可以使用虚拟试衣的"真实贴身"模式了。
    echo.
) else (
    echo.
    echo ========================================
    echo 安装失败！
    echo ========================================
    echo.
    echo 请检查网络连接或手动运行：
    echo pip install dashscope
    echo.
)

pause
