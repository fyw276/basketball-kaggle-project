# 环境配置指南

## 项目初始化

...

## 依赖安装

...

## 启动后端

```powershell
cd "d:\Users\omen\OneDrive\桌面\clothing-assistant\backend"
& d:/Users/omen/OneDrive/桌面/clothing-assistant/.venv/Scripts/Activate.ps1
python -m uvicorn app.main:app --port 8010
```

> **注意**：CatVTON + CUDA 环境下**禁止使用 `--reload`**，热重载会导致 CUDA context 销毁与 GPU 显存碎片，推理异常。开发时如需热重载，先设置 `CATVTON_ENABLED=false` 禁用 CatVTON。

## 常用命令

...
