# 虚拟试衣功能快速修复指南 ⚡

## 🔍 问题

虚拟试衣的"真实贴身"和"稳定"模式无法使用

## 🎯 根本原因

**dashscope 包未安装**

## ✅ 快速修复（3步）

### 1️⃣ 安装 dashscope

**Windows:**
```bash
cd backend
install_dashscope.bat
```

**Linux/Mac:**
```bash
cd backend
chmod +x install_dashscope.sh
./install_dashscope.sh
```

**或手动安装:**
```bash
pip install "dashscope>=1.20.0,<2.0.0"
```

### 2️⃣ 验证安装

```bash
cd backend
python test_dashscope_status.py
```

看到 "✓ 所有检查通过" 即可。

### 3️⃣ 重启服务

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

## 📋 已完成的代码修复

✅ 添加了 DashScope 配置项到 `config.py`
✅ 改进了错误处理和诊断信息
✅ 创建了诊断工具和安装脚本
✅ 提供了详细的错误提示

## 📚 详细文档

- **完整修复指南**: `backend/TRYON_FIX_README.md`
- **修复总结**: `TRYON_FIX_SUMMARY.md`
- **诊断工具**: `backend/test_dashscope_status.py`

## 🆘 需要帮助？

运行诊断工具查看详细信息：
```bash
cd backend
python test_dashscope_status.py
```

---

**修复时间**: 2026-04-22
**状态**: ✓ 代码已修复，等待安装 dashscope 包
