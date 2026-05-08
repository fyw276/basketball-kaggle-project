# 2026-05-08 虚拟试衣 v2 (TryOn v2) 模块化重构与真实模式修复

## 概述

本次更新主要包含后端虚拟试衣 v2 服务的模块化重构，以及修复了真实模式（Realistic）下可能出现的“衣服多层/贴纸感”问题。通过禁用后处理中的叠加保护，将图像合成的任务完全交由 CatVTON 的内绘网络处理，极大提升了生成图像的真实度与自然感。此外，梳理了后端各 AI 服务模块并同步了完整的服务模块开发指南。

**完成时间**: 2026-05-08
**版本更新**: v1.6.0 → v1.7.0
**PR 类型**: refactor + bugfix + docs

---

## 核心更新

### 1. 真实模式 (Realistic Mode) 修复与优化
**问题**: 在 Realistic 模式下，当检测到源衣物包含较强纹理时，原有逻辑会使用 alpha overlay 的方式将源衣服硬覆盖至 AI 生成图上，导致双重衣物错位或出现剥离感（"贴纸感"）。
**修复**:
- 在 API 中将 `pattern_score` 强制重置为 0.0，关闭叠加保护逻辑。
- 让 CatVTON 的 Diffusion Inpainting 完全接管衣服生成，由于生成模型的本身能力已经能够很好地捕捉纹理与光影，最终效果更逼真且与原图完美贴合。
- 引入了过渡状态的 `realistic_v2` 模式保留备用逻辑测试路径。

### 2. 后端服务模块化 (Service Modules Refactoring)
为了解决原先 `vton_inference_service` 及脚本过度紧耦合、不易维护的问题，我们拆分了以下服务模块，使架构更加清晰：
- `human_parsing.py`: 人体图像解析服务 (SCHP 模型)
- `densepose_service.py`: 姿态及身体网格提取服务 (DensePose)
- `sam_mask.py`: 服装蒙版自动提取 (Segment Anything Model)
- `person_crop.py`: 人物主体识别与智能裁剪
- `garment_alignment.py`: 姿态对齐与衣物形变
- `cloth_warp.py` 与 `garment_classifier.py` 进一步完善。
这些模块使预处理工作流 (Preprocessing Pipeline) 阶段的扩展和单独测试变得可能。

### 3. 文档同步更新
- **`SERVICE_MODULES_GUIDE.md`**: 全新创建，详细记录了重构之后各独立服务模块的职责、调用方式与输入输出契约。
- **`README.md` 与 `PROJECT_STATUS.md`**: 更新了版本号与重构详情。

---


### 1. CatVTON 子进程路径修复

**问题**: `catvton_engine_client.py` 中的 `workspace_root` 路径计算多上了一级目录，导致 `catvton_runner.py` 找不到。

**修复**:
```python
# 修复前 (错误)
workspace_root = Path(__file__).parent.parent.parent.parent.parent  # 多上一级

# 修复后 (正确)
current = Path(__file__).resolve()
workspace_root = current
for _ in range(5):  # 从 tryon_v2/ 到项目根目录
    workspace_root = workspace_root.parent
```

**影响文件**: `backend/app/services/tryon_v2/catvton_engine_client.py`

### 2. 子进程工作目录修复

**问题**: 子进程工作目录指向 `backend/app/`，但 runner 脚本在项目根目录。

**修复**:
```python
# 修复前
proc = subprocess.Popen(cmd, cwd=str(backend_dir), ...)  # 错误

# 修复后
proc = subprocess.Popen(cmd, cwd=str(workspace_root), ...)  # 正确
```

### 3. CatVTON 路径自动检测

**功能**: 添加 `_get_catvton_path()` 函数，自动检测以下路径（按优先级）：
1. `CATVTON_PATH` 环境变量配置
2. `D:\models\CatVTON_full`（完整下载版本）
3. `D:\models\CatVTON`（HuggingFace 快照版本）

**影响**: 无需用户手动修改配置，系统自动识别安装位置

### 4. 实时日志流式传输

**功能**: 使用 Python `threading` 实时流式传输子进程的 stdout/stderr，在主进程终端实时显示 CatVTON 执行日志。

**好处**:
- 调试时能实时看到 CatVTON 的执行步骤
- 显著提升了诊断效率
- 若子进程卡住能及时发现

**实现**:
```python
def stream_output(stream, lines_list, lock, prefix):
    """读取流逐行传输，实时日志"""
    for line in iter(stream.readline, ''):
        if line:
            with lock:
                lines_list.append(line)
            logger.info(f"[CATVTON] {prefix}: {line}")
```

### 5. 请求日志中间件

**新增**: `RequestLoggingMiddleware` 在 `backend/app/main.py`

**作用**: 记录所有 API 请求的起点和终点，便于调试：
```
[REQUEST] POST /api/v2/tryon/garment - started
[REQUEST] POST /api/v2/tryon/garment - completed 200 in 45000.5ms
```

---

## 白盒调试工具

### 新增 `debug_mode` 参数

在 `POST /api/v2/tryon/garment` 中添加白盒调试选项：

```bash
curl -X POST "http://127.0.0.1:8010/api/v2/tryon/garment" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "garment_file=@garment.jpg" \
  -F "person_file=@person.jpg" \
  -F "debug_mode=preprocess_only"  # 或 full
```

### 三种调试模式

| 模式 | 含义 | 耗时 | 用途 |
|------|------|------|------|
| `off` | 正常推理（默认） | 30-60s | 生产使用 |
| `preprocess_only` | 仅 mask + 姿态 | 3-5s | 快速验证遮罩质量 |
| `full` | 完整管线 + 保存中间产物 | 30-60s | 调试最终效果 |

### 中间产物保存

启用 `CATVTON_DEBUG_DIR` 环境变量后，每次请求自动保存：

```
debug_output/tryon_20260427_143000_abc123/
├── 01_input_person.jpg         # 原始输入
├── 02_input_garment.jpg
├── 03_mask.png                 # ★ 关键：衣服区域遮罩
├── 04_pose_keypoints.jpg       # ★ 关键：姿态骨架
├── 06_person_resized.jpg       # 缩放后输入
├── 07_garment_resized.jpg
├── 08_mask_resized.jpg
├── 09_mask_overlay.jpg         # ★ mask 叠加人物图
├── 10_result_raw.jpg           # 扩散输出
└── 11_result_final.jpg         # 最终结果（重绘后）
```

**关键文件**:
- `03_mask.png`: 若 mask 范围错误（太大/太小/包含脸部），直接从这里发现
- `04_pose_keypoints.jpg`: 若关键点检测有误（肩膀位置偏移），从这里调试
- `09_mask_overlay.png`: 直观验证 mask 是否覆盖了正确区域

---

## 极限 VRAM 优化

### 新配置项

在 `backend/.env` 中新增：

```env
# 强制使用 fp16（RTX 4060 Laptop 推荐）
CATVTON_FORCE_FP16=true

# VAE 分片推理（降低峰值显存 40-60%）
CATVTON_ENABLE_VAE_SLICING=true

# xformers 高效注意力（无则降级到 PyTorch FlashAttention）
CATVTON_ENABLE_XFORMERS=true

# 极端显存不足时启用（UNet/VAE CPU 卸载）
CATVTON_CPU_OFFLOAD=false

# 一键低显存模式（自动应用全部优化）
CATVTON_LOW_VRAM_MODE=false
```

### VRAM 占用对比

| 配置 | VRAM 需求 | 速度影响 | 推荐场景 |
|------|----------|--------|--------|
| 默认（bf16） | ~8GB | 基准 | RTX 3060+ |
| fp16 | ~6GB | +5% | RTX 4060 |
| +VAE slicing | -40% 峰值 | +10% | 8GB 卡优化 |
| +CPU offload | ~4GB | +50% | 4GB 卡救急 |
| 低显存模式 | ~4GB | +80% | RTX 3050 |

### 推理步骤日志

`catvton_runner.py` 现添加明显的步骤日志：

```
[CATVTON-STEP] 开始生成衣服遮罩 (type=upper)...
[CATVTON-STEP] 遮罩生成完成
[CATVTON-STEP] 正在加载 CatVTON Pipeline (precision=bf16)...
[CATVTON-STEP] 正在缩放图片...
[CATVTON-STEP] 开始 CatVTON 扩散推理 (steps=50, guidance=2.5)...
[CATVTON-STEP] 推理完成，耗时 45.2s
```

---

## 文件修改清单

### 核心修改

| 文件 | 修改内容 | 重要性 |
|------|----------|--------|
| `backend/app/services/tryon_v2/catvton_engine_client.py` | 路径计算修复、子进程 cwd、自动检测、实时日志 | ⭐⭐⭐ |
| `vton_inference_service/catvton_runner.py` | 白盒调试、VRAM 优化、步骤日志、无缓冲输出 | ⭐⭐⭐ |
| `backend/app/main.py` | `RequestLoggingMiddleware` 新增 | ⭐⭐ |
| `backend/app/api/tryon_v2.py` | `debug_mode` 参数、`debug_session_dir` 返回 | ⭐⭐ |
| `backend/app/core/config.py` | 新增 VRAM 优化配置项 | ⭐ |
| `backend/app/core/logging.py` | Windows 安全日志（enqueue=True）| ⭐ |

### 文档更新

| 文件 | 更新内容 |
|------|----------|
| `README.md` | 日期和状态更新 |
| `PROJECT_STATUS.md` | 版本升级 v1.3 → v1.4，新增本次更新说明 |
| `CATVTON_INSTALL_GUIDE.md` | 重新组织结构，强调 `CatVTON_full` 完整版本 |
| `TRYON_FIX_SUMMARY.md` | 完全改写，聚焦本次路径和日志修复 |

---

## 验证方法

### 1. 检查模型文件

```powershell
# 验证 CatVTON 模型是否存在
Test-Path "D:\models\CatVTON_full\mix-48k-1024\attention\model.safetensors"
```

预期输出：`True`

### 2. 重启后端查看日志

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

观察终端输出应包含：
```
[DEBUG] __file__ = ...catvton_engine_client.py
[DEBUG] workspace_root = ...clothing-assistant
[DEBUG] runner_path = ...\vton_inference_service\catvton_runner.py exists=True
[CATVTON] 启动子进程执行 CatVTON...
```

### 3. 调用 API 测试

```bash
curl -X POST "http://127.0.0.1:8010/api/v2/tryon/garment" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "garment_file=@garment.jpg" \
  -F "person_file=@person.jpg" \
  -F "mode=realistic" \
  -F "debug_mode=preprocess_only"
```

预期返回：
```json
{
  "status": "preprocess_only_success",
  "message": "预处理完成（diffusion 未运行）",
  "metadata": {
    "engine": "catvton",
    "debug_session_dir": "/path/to/debug_session"
  },
  "debug_session_dir": "/path/to/debug_session"
}
```

### 4. 检查调试文件

打开返回的 `debug_session_dir`：
- `03_mask.png` 应显示白色区域覆盖了衣服区域
- `04_pose_keypoints.jpg` 应显示清晰的骨架线
- `09_mask_overlay.jpg` 应显示 mask 与原图的叠加

---

## 常见问题

### Q: CatVTON runner 脚本找不到的错误仍然出现怎么办？

A: 确认路径结构：
```powershell
ls vton_inference_service/catvton_runner.py  # 应该存在
ls backend/app/services/tryon_v2/catvton_engine_client.py  # 应该存在
```

### Q: 模型下载失败（HuggingFace 网络问题）怎么办？

A: 配置镜像源：
```env
HF_HOME=D:\hf-cache
HF_ENDPOINT=https://hf-mirror.com
```

### Q: preprocess_only 模式超时怎么办？

A: 调整超时配置：
```env
CATVTON_TIMEOUT_SECONDS=600  # 改为 900 或更大
```

### Q: 显存 OOM（out of memory）怎么办？

A: 依次尝试：
1. 启用 `CATVTON_FORCE_FP16=true`
2. 启用 `CATVTON_ENABLE_VAE_SLICING=true`
3. 启用 `CATVTON_CPU_OFFLOAD=true`
4. 启用 `CATVTON_LOW_VRAM_MODE=true`

---

## 技术支持

若问题仍未解决，请收集以下信息：

1. 后端启动日志（查找 `[CATVTON]` 标记）
2. API 请求日志（查找 `[REQUEST]` 标记）
3. 诊断脚本输出：
   ```bash
   python backend/scripts/diagnose_catvton.py
   ```
4. 返回的 `metadata` 完整内容
5. `debug_session_dir` 中的关键中间产物（03_mask.png, 04_pose_keypoints.jpg）

---

**修复完成时间**: 2026-04-27
**下一步**: 用户验证 + 迭代反馈
