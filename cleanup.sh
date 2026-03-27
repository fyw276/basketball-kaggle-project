#!/bin/bash
# 清理项目中的临时文件和缓存
# 使用方法: ./cleanup.sh

echo "开始清理项目..."

# 清理 Python 缓存
echo "清理 Python 缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find . -type f -name ".coverage" -delete 2>/dev/null
find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null

# 清理 Flutter/Dart 缓存
echo "清理 Flutter/Dart 缓存..."
rm -rf mobile/.dart_tool 2>/dev/null
rm -rf mobile/build 2>/dev/null

# 清理日志文件
echo "清理日志文件..."
find . -type f -name "*.log" -delete 2>/dev/null

# 清理临时文件
echo "清理临时文件..."
rm -rf backend/uploads/* 2>/dev/null

echo "清理完成！"
echo "建议重启 VS Code 以应用更改。"
