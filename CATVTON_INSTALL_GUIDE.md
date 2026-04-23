# CatVTON 安装指南 — 本地高质量虚拟试衣

## CatVTON 是什么？

**CatVTON** 是一个轻量级虚拟试衣扩散模型，专门解决"商品图 → 真人试穿"的问题：

| 特性 | 说明 |
|---|---|
| 质量 | 业界最高水平（ICLR 2025），远超当前 Pipeline A 的几何拼贴 |
| VRAM | **8GB** 即可运行（bf16 混合精度）— 适合你的 RTX 4060 Laptop |
| 预处理 | **自动遮罩生成**（SCHP + DensePose），无需手动标注 |
| 速度 | 约 30-60 秒/张图 |
| 开源 | Apache 2.0 许可 |

## 为什么选择 CatVTON 而不是其他方案？

```
Pipeline A（当前） = 2D 拼贴 → 永远像 PS 叠加
Bailian（阿里）   = 可能换脸/颜色失真
IDM-VTON         = 需要 16-18GB VRAM（你的机器跑不动）
CatVTON          = 真实光影 + 颜色保真 + 8GB VRAM ✅
```

---

## 安装步骤

### 第一步：克隆 CatVTON 仓库

```bash
# 在合适的位置克隆（如 D:\models\CatVTON）
git clone https://github.com/Zheng-Chong/CatVTON.git D:\models\CatVTON
cd D:\models\CatVTON
```

### 第二步：创建 conda 环境（Python 3.9）

```bash
# 如果没有 conda，先安装：https://docs.conda.io/en/latest/miniconda.html
conda create -n catvton python==3.9.0
conda activate catvton
```

### 第三步：安装 PyTorch + CUDA

```bash
# RTX 4060 Laptop = CUDA 11.8 或 12.1
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118
```

### 第四步：安装 CatVTON 依赖

```bash
# 在 CatVTON 目录下
pip install -r requirements.txt

# 额外依赖（CatVTON 需要）
pip install accelerate transformers diffusers opencv-python pillow

# detectron2（用于 DensePose，自动遮罩生成必需）
# 注意：detectron2 在 Windows 上安装复杂，如果遇到问题，看下方"Windows 兼容说明"
pip install 'git+https://github.com/facebookresearch/detectron2.git'
```

### 第五步：下载预训练权重

CatVTON 权重会在**首次运行时自动从 HuggingFace 下载**，无需手动下载。

下载的内容包括：
- `runwayml/stable-diffusion-inpainting`（SD v1.5 基础模型）
- `zhengchong/CatVTON`（CatVTON 注意力权重）
- `DensePose` 权重（用于自动遮罩生成）
- `SCHP` 权重（用于人像分割）

**首次运行大约需要下载 5-10GB 文件，请保持网络连接。**

### 第六步：验证安装

```bash
# 在 CatVTON 目录下
python app.py --output_dir="resource/demo/output" --mixed_precision="bf16"
```

如果看到 Gradio 界面，说明安装成功。关闭后：

```bash
# Ctrl+C 停止
```

---

## 启动 CatVTON 推理服务

### 方法 A：通过 vton_inference_service（推荐集成方式）

**1. 修改 backend/.env：**

```env
# 取消注释并修改路径为你的实际路径
CATVTON_ENABLED=true
CATVTON_PATH=D:\models\CatVTON
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon
VTON_INFERENCE_TIMEOUT_SECONDS=600
CATVTON_STEPS=50
CATVTON_GUIDANCE=2.5
```

**2. 启动 CatVTON 推理服务（端口 8011）：**

```bash
# 在 clothing-assistant 根目录
cd vton_inference_service
pip install fastapi uvicorn httpx pillow
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8011
```

**3. 验证服务可用：**

```bash
# 新开一个终端
curl http://127.0.0.1:8011/health
```

应该返回：

```json
{
  "status": "ok",
  "catvton_available": true,
  "stub_mode": false
}
```

**4. 启动 backend：**

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 方法 B：直接运行（不需要服务）

```bash
cd vton_inference_service
python catvton_engine.py \
    --person /path/to/person.jpg \
    --garment /path/to/garment.jpg \
    --output /path/to/result.jpg \
    --type upper \
    --steps 50 \
    --guidance 2.5 \
    --seed 42
```

---

## Windows 兼容说明

### detectron2 安装问题

detectron2 在 Windows 上有时安装困难。如果遇到：

```bash
# 方法1：使用预编译 wheel
pip install detectron2 -f https://dl.fbaipublicfiles.com/detectron2/wheels/cpu/index.html

# 方法2：从源码编译（需要 Visual Studio Build Tools）
git clone https://github.com/facebookresearch/detectron2.git
cd detectron2
python setup.py build
pip install .
```

### CUDA 版本问题

RTX 4060 Laptop 通常支持 CUDA 11.8 或 12.1。检查你的版本：

```bash
nvidia-smi
```

右上角显示 CUDA 版本。如果显示 11.8，用：

```bash
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu118
```

如果显示 12.1，用：

```bash
pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cu121
```

---

## 参数调优建议

### cloth_type（服装类型）

| 类型 | 说明 | 示例 |
|---|---|---|
| `upper` | 上装 | 衬衫、T恤、夹克、毛衣 |
| `lower` | 下装 | 裤子、裙子 |
| `overall` | 全身装 | 连衣裙 |

### inference_steps（推理步数）

| 步数 | 速度 | 质量 |
|---|---|---|
| 30 | 快（~20秒） | 基本可用 |
| **50** | 中等（~40秒） | **推荐** |
| 80 | 慢（~80秒） | 最佳细节 |

### guidance_scale（CFG 强度）

| 值 | 效果 |
|---|---|
| 1.5 | 柔和，可能变形较大 |
| **2.5** | **推荐，平衡保真和自然度** |
| 4.0 | 服装保真度高，可能生硬 |

### seed（随机种子）

- `-1` = 每次随机生成不同结果
- 固定数字 = 可复现结果（调试用）

---

## 故障排除

### 错误：CUDA out of memory

```bash
# 减小图像尺寸
CATVTON_WIDTH=512
CATVTON_HEIGHT=768

# 或使用 fp16 精度（更省显存但质量稍低）
CATVTON_MIXED_PRECISION=fp16
```

### 错误：detectron2 导入失败

```bash
# 在 CatVTON 环境中
pip install 'git+https://github.com/facebookprofi.github.com/detectron2.git'
```

### 错误：超时（timeout）

```bash
# 增加超时时间
CATVTON_TIMEOUT_SECONDS=900
```

### 错误：CatVTON not available

检查路径是否正确：

```bash
# 确认路径存在
dir D:\models\CatVTON

# 确认有 model 目录
ls D:\models\CatVTON/model
```

---

## 架构说明

```
前端用户上传
    ↓
Backend API (tryon_v2.py)
    ↓
catvton_client.py — 调用远程服务
    ↓
vton_inference_service (main.py) — 端口 8011
    ↓
catvton_engine.py — CatVTON 核心推理
    ↓
SCHP + DensePose — 自动遮罩生成
    ↓
结果图返回给用户
```

---

## 对比测试

### 测试命令（需要先安装并启动服务）：

```python
import httpx
from PIL import Image
import io

# 1. Pipeline A（当前方案）— 贴图感
# mode=strict → 走 Pipeline A（几何变形）

# 2. CatVTON（新方案）— 照片级真实
# 设置 mode=balanced 或 replace，然后通过 VTON_INFERENCE_URL 调用

# 3. Bailian（阿里云）
# DASHSCOPE_TRYON_ENABLED=true
```

---

## 下一步

安装完成后，你可以通过前端正常使用 CatVTON 试衣。推荐使用 `mode=replace`，系统会自动选择 CatVTON 作为推理引擎。
