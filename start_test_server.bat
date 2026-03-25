@echo off
echo 正在启动测试服务器...
echo.
echo 测试工具地址: http://localhost:8080/test_api.html
echo.
echo 按 Ctrl+C 停止服务器
echo.
cd backend
python -m http.server 8080
