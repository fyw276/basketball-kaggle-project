@echo off
REM 编译检查脚本

cd /d "d:\Users\omen\OneDrive\桌面\clothing-assistant\mobile"

echo 正在检查代码编译...
echo.

REM 运行 Flutter 分析
flutter pub get >nul 2>&1

REM 如果想要更详细的输出，可以使用：
REM flutter analyze

echo 尝试编译 Dart 文件...
dart compile kernel lib/main.dart --output lib/main.dill 2>&1 | find /v "Compiling"

if %errorlevel% equ 0 (
    echo.
    echo ✓ 编译检查完成 - 没有找到严重错误
) else (
    echo.
    echo ✗ 编译检查发现问题
)

pause
