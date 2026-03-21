# 🚀 快速开始

## 遇到问题？一键解决

```bash
cd backend
fix_everything.bat
```

这个脚本会自动：
- 检查 Python 环境
- 清理旧的虚拟环境
- 重新安装所有依赖
- 启动服务器

## 详细说明

查看 `backend/START_HERE.md` 获取完整指南。

## 3 步启动

1. 打开命令提示符（CMD）
2. 运行：
```bash
cd backend
fix_everything.bat
```
3. 访问 http://localhost:8000/docs

就这么简单！

## 常见问题

- **Pillow 安装失败？** - 正常，我们跳过了它（任务 5 才需要）
- **字符显示乱码？** - 已修复（脚本自动设置 UTF-8）
- **Python 未安装？** - 访问 https://www.python.org/downloads/

## 需要帮助？

- `backend/START_HERE.md` - 完整启动指南
- `backend/QUICK_FIX.md` - Pillow 问题解决
- `backend/TROUBLESHOOTING.md` - 详细故障排查
- `backend/DEPENDENCIES.md` - 依赖说明

## 成功标志

看到这个就成功了：
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

然后访问 http://localhost:8000/docs 查看 API 文档！
