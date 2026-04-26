# 虚拟试衣功能修复总结

## 2026-04-26 CatVTON 推理修复

### 已修复

1. **CatVTON 参数兼容性** ✓
   - 移除了 `attention_slicing="auto"` 和 `enable_xformers=True`（CatVTONPipeline 不接受这些参数）
   - 添加了 `--precision` 参数支持 `bf16/fp16/fp32` 精度控制

2. **MediaPipe 0.10 API 适配** ✓
   - `catvton_runner.py` 中 MediaPipe `Image.create_from_array` 在 0.10.x 中不存在，改为临时文件方式（`create_from_file`）
   - 在 `.venv` 中安装了 `mediapipe 0.10.33`

3. **CatVTON 配置增强** ✓
   - 新增 `CATVTON_MIXED_PRECISION`、`CATVTON_CPU_OFFLOAD`、`CATVTON_DEBUG_DIR` 三个配置项
   - `catvton_engine_client.py` 传递 precision/offload 参数到 subprocess

4. **终端日志改进** ✓
   - `logging.py` 检测 `sys.stdout.isatty()`，在 PowerShell 等非 TTY 环境中禁用 loguru `colorize`
   - `.env` 和 `run_uvicorn_dev.ps1` 添加 `TF_ENABLE_ONEDNN_OPTS=0` 消除 TensorFlow 警告

> **注意**：本项目使用 **MediaPipe PoseLandmarker** 生成人体掩码，**无需 detectron2 / DensePose / SCHP**。

## 问题诊断（历史）

通过诊断工具 `backend/test_dashscope_status.py` 发现：

### ✓ 已修复的问题

1. **配置加载问题** ✓
   - 在 `backend/app/core/config.py` 中添加了完整的 DashScope 和 VTON 配置项
   - 配置现在可以正确从 `.env` 文件加载

2. **错误处理改进** ✓
   - 改进了 `backend/app/services/bailian_tryon_client.py` 的错误处理
   - 添加了详细的错误诊断信息（error_type, specific_hint等）
   - 改进了 `backend/app/api/tryon_v2.py` 的错误响应

3. **诊断工具** ✓
   - 创建了 `backend/test_dashscope_status.py` 诊断脚本
   - 创建了安装脚本 `install_dashscope.bat` 和 `install_dashscope.sh`
   - 创建了详细的修复指南 `backend/TRYON_FIX_README.md`

### ✗ 需要用户操作的问题

**dashscope 包未安装** - 这是导致虚拟试衣功能无法使用的根本原因

## 修复步骤（用户需要执行）

### 步骤1：安装 dashscope 包

选择以下任一方法：

#### 方法A：使用安装脚本（推荐）

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

#### 方法B：手动安装

```bash
cd backend
pip install "dashscope>=1.20.0,<2.0.0"
```

### 步骤2：验证安装

```bash
cd backend
python test_dashscope_status.py
```

如果看到"✓ 所有检查通过"，说明修复成功。

### 步骤3：重启后端服务

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 步骤4：测试虚拟试衣功能

1. 打开Flutter应用
2. 进入虚拟试衣页面
3. 选择"真实贴身"或"稳定"模式
4. 上传人物照片和衣服照片
5. 点击"开始试衣"

## 代码改进详情

### 1. 配置文件改进 (`backend/app/core/config.py`)

添加了以下配置项：

```python
# DashScope / Bailian (阿里云百炼)
DASHSCOPE_TRYON_ENABLED: bool = False
DASHSCOPE_API_KEY: str = ""
DASHSCOPE_TRYON_MODEL: str = "wanx2.1-imageedit"
DASHSCOPE_TRYON_MODEL_TOP: str = ""
DASHSCOPE_TRYON_MODEL_BOTTOM: str = ""
DASHSCOPE_TRYON_MODEL_SKIRT: str = ""
DASHSCOPE_TRYON_FUNCTION: str = ""
DASHSCOPE_TRYON_DOWNLOAD_TIMEOUT_SECONDS: int = 120
DASHSCOPE_TRYON_FALLBACK_LOCAL: bool = True

# Remote VTON service
VTON_INFERENCE_URL: str = ""
VTON_INFERENCE_TIMEOUT_SECONDS: int = 2400
VTON_INFERENCE_API_KEY: str = ""
```

### 2. 错误处理改进 (`backend/app/services/bailian_tryon_client.py`)

- 添加了 `error_type` 字段（dependency_missing, api_error等）
- 添加了 `specific_hint` 字段提供具体的错误提示
- 改进了异常捕获，能够识别网络超时、SSL错误、认证失败等
- 根据错误代码自动提供相应的解决方案

### 3. API错误响应改进 (`backend/app/api/tryon_v2.py`)

- 增强了 `replace_debug.bailian` 字段的信息
- 根据错误类型提供更具体的提示：
  - "dashscope 包未安装" → 提示安装命令
  - API key 无效 → 明确指出认证问题
  - 额度不足 → 提示检查额度
  - 网络超时 → 提示检查网络连接

## 错误信息示例

### 修复前

```json
{
  "message": "替换试衣上游不可用或未成功",
  "action_hint": "百炼未成功：请检查 key/额度/模型权限/网络；查看 detail.replace_debug.bailian"
}
```

### 修复后

```json
{
  "message": "替换试衣上游不可用或未成功",
  "action_hint": "百炼失败：dashscope 包未安装，请运行 pip install dashscope",
  "replace_debug": {
    "bailian": {
      "configured": true,
      "status": "error",
      "message": "dashscope 未安装",
      "reason": "dashscope_missing",
      "error_type": "dependency_missing",
      "specific_hint": "",
      "action_required": "pip install dashscope"
    }
  }
}
```

## 诊断工具输出示例

```
============================================================
虚拟试衣功能诊断工具
============================================================

============================================================
测试 1: 检查 dashscope 包
============================================================
✓ dashscope 包已安装

============================================================
测试 2: 检查配置
============================================================
DASHSCOPE_TRYON_ENABLED: True
DASHSCOPE_API_KEY: sk-66c18c6...3e04
✓ 配置正确

============================================================
测试 3: 检查百炼客户端
============================================================
✓ 百炼客户端配置正确

============================================================
诊断总结
============================================================
dashscope包: ✓ 通过
配置: ✓ 通过
百炼客户端: ✓ 通过

============================================================
✓ 所有检查通过！虚拟试衣功能应该可以正常使用。

下一步:
1. 重启后端服务
2. 在Flutter应用中测试虚拟试衣功能
============================================================
```

## 文件清单

### 修改的文件

1. `backend/app/core/config.py` - 添加DashScope和VTON配置项
2. `backend/app/services/bailian_tryon_client.py` - 改进错误处理
3. `backend/app/api/tryon_v2.py` - 改进错误响应

### 新增的文件

1. `backend/test_dashscope_status.py` - 诊断工具
2. `backend/install_dashscope.bat` - Windows安装脚本
3. `backend/install_dashscope.sh` - Linux/Mac安装脚本
4. `backend/TRYON_FIX_README.md` - 详细修复指南
5. `TRYON_FIX_SUMMARY.md` - 本文件（修复总结）

## 常见问题

### Q: 安装dashscope后仍然报错怎么办？

A: 运行诊断工具查看详细信息：
```bash
cd backend
python test_dashscope_status.py
```

### Q: 如何验证API Key是否有效？

A: 诊断工具会显示API Key的前10位和后4位。如果配置正确但仍然失败，可能是：
- API Key 已过期
- API 额度不足
- 模型权限未开通

### Q: 是否需要配置远程VTON服务？

A: 不需要。安装dashscope后，百炼API即可正常工作。远程VTON服务是可选的备用方案。

### Q: "稳定"模式和"真实贴身"模式有什么区别？

A:
- **稳定模式（balanced）**: 使用方案A（pipeline A），基于图像变形和融合
- **真实贴身模式（replace）**: 使用百炼API或远程VTON，基于生成式AI，效果更真实

## 技术支持

如果问题仍未解决，请提供以下信息：

1. 诊断工具的完整输出
2. 错误响应中的 `replace_debug` 完整内容
3. 后端日志（查找包含"Bailian try-on failed"的行）
4. Python版本和操作系统信息

---

**修复完成时间**: 2026-04-22
**修复状态**: ✓ 代码修复完成，等待用户安装dashscope包
