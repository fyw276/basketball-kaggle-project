# 专用VTON服务部署指南

## 📋 目录

1. [快速开始（Stub模式）](#快速开始stub模式)
2. [部署OOTDiffusion（推荐）](#部署ootdiffusion推荐)
3. [部署IDM-VTON（备选）](#部署idm-vton备选)
4. [配置主应用](#配置主应用)
5. [测试验证](#测试验证)
6. [故障排除](#故障排除)

---

## 快速开始（Stub模式）

### 步骤1：启动Stub服务

Stub模式用于快速验证服务连接，不需要GPU和模型权重。

```powershell
# Windows
cd vton_inference_service
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set VTON_STUB_MODE=true
set PORT=8011
uvicorn main:app --host 0.0.0.0 --port 8011
```

```bash
# Linux/Mac
cd vton_inference_service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export VTON_STUB_MODE=true
export PORT=8011
uvicorn main:app --host 0.0.0.0 --port 8011
```

### 步骤2：配置主应用

编辑 `backend/.env`：

```env
# 启用远程VTON服务
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon

# 可选：API密钥（如果设置了VTON_SERVICE_API_KEY）
# VTON_INFERENCE_API_KEY=your-shared-secret

# 禁用百炼（因为不支持参考图）
DASHSCOPE_TRYON_ENABLED=false

# 禁用本地diffusion兜底
TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=false
```

### 步骤3：重启主应用

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 步骤4：测试

访问 `http://127.0.0.1:8011/health` 应该看到：

```json
{
  "status": "ok",
  "stub_mode": true,
  "note": "Set VTON_STUB_MODE=false when wiring real OOTDiffusion/IDM inference"
}
```

---

## 部署OOTDiffusion（推荐）

### 系统要求

- **GPU**: NVIDIA GPU with 8GB+ VRAM (推荐 RTX 3060/4060 或更高)
- **CUDA**: 11.8 或 12.1
- **Python**: 3.10 或 3.11
- **磁盘空间**: ~20GB (模型权重)

### 步骤1：克隆OOTDiffusion仓库

```bash
cd ~
git clone https://github.com/levihsu/OOTDiffusion.git
cd OOTDiffusion
```

### 步骤2：创建独立环境

```bash
# 创建独立的conda环境（推荐）
conda create -n ootd python=3.10
conda activate ootd

# 或使用venv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows
```

### 步骤3：安装依赖

```bash
# 安装PyTorch (CUDA 11.8)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 或 CUDA 12.1
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 安装OOTDiffusion依赖
pip install -r requirements.txt
```

### 步骤4：下载模型权重

```bash
# 设置Hugging Face镜像（国内用户）
export HF_ENDPOINT=https://hf-mirror.com

# 下载权重（约15GB）
python -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='levihsu/OOTDiffusion', local_dir='./checkpoints')
"
```

### 步骤5：测试OOTDiffusion

```bash
# 使用官方示例测试
python run/run_ootd.py \
  --cloth_path ./examples_dc/cloth/03244_00.jpg \
  --model_path ./examples_dc/model/model_1.png \
  --category 0 \
  --output_path ./output
```

**category参数：**
- `0`: 上装 (upper body)
- `1`: 下装 (lower body)
- `2`: 裙装 (dress)

### 步骤6：集成到VTON服务

创建 `vton_inference_service/ootd_engine.py`：

```python
"""
OOTDiffusion inference engine for VTON service.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import torch
from PIL import Image

# 添加OOTDiffusion路径
OOTD_PATH = os.environ.get("OOTD_PATH", str(Path.home() / "OOTDiffusion"))
sys.path.insert(0, OOTD_PATH)

# 导入OOTDiffusion模块
try:
    from run.run_ootd import OOTDiffusionModel
except ImportError:
    OOTDiffusionModel = None


class OOTDEngine:
    """OOTDiffusion inference wrapper."""

    def __init__(self, checkpoint_path: Optional[str] = None):
        if OOTDiffusionModel is None:
            raise ImportError(
                "OOTDiffusion not found. Please install it first. "
                f"Expected path: {OOTD_PATH}"
            )

        self.checkpoint_path = checkpoint_path or os.path.join(OOTD_PATH, "checkpoints")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        if self.device == "cpu":
            raise RuntimeError("OOTDiffusion requires CUDA GPU")

        # 初始化模型
        self.model = OOTDiffusionModel(
            checkpoint_path=self.checkpoint_path,
            device=self.device
        )

        print(f"OOTDEngine initialized on {self.device}")

    def infer(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        category: int = 0,
        num_inference_steps: int = 20,
        guidance_scale: float = 2.0,
    ) -> Image.Image:
        """
        Run OOTDiffusion inference.

        Args:
            person_image: Person full-body image
            garment_image: Garment product image
            category: 0=upper, 1=lower, 2=dress
            num_inference_steps: Number of diffusion steps
            guidance_scale: Guidance scale for diffusion

        Returns:
            Result image with person wearing the garment
        """
        # 预处理图像
        person_image = person_image.convert("RGB")
        garment_image = garment_image.convert("RGB")

        # 调用OOTDiffusion推理
        result = self.model.generate(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )

        return result


# 全局单例
_engine: Optional[OOTDEngine] = None


def get_engine() -> OOTDEngine:
    """Get or create OOTDEngine singleton."""
    global _engine
    if _engine is None:
        _engine = OOTDEngine()
    return _engine
```

### 步骤7：更新VTON服务

修改 `vton_inference_service/main.py`，在 `tryon_v1` 函数中添加：

```python
# 在文件顶部添加导入
try:
    from ootd_engine import get_engine
    OOTD_AVAILABLE = True
except ImportError:
    OOTD_AVAILABLE = False
    print("Warning: OOTDiffusion not available, using stub mode")

# 在 tryon_v1 函数中替换stub逻辑
@app.post("/v1/tryon")
async def tryon_v1(
    request: Request,
    garment_file: UploadFile = File(...),
    person_file: UploadFile = File(...),
    model_gender: str = Form("neutral"),
    garment_category: str = Form(""),
    prompt: str = Form(""),
):
    _check_bearer(request)

    g_bytes = await garment_file.read()
    p_bytes = await person_file.read()
    if not g_bytes or not p_bytes:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "empty garment_file or person_file",
            },
        )

    try:
        person_im = Image.open(io.BytesIO(p_bytes))
        garment_im = Image.open(io.BytesIO(g_bytes))
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"invalid image: {e}"},
        )

    cat_hint = _ootd_category_hint(garment_category)

    # 使用OOTDiffusion或Stub
    if OOTD_AVAILABLE and not VTON_STUB_MODE:
        try:
            engine = get_engine()
            result_im = engine.infer(
                person_image=person_im,
                garment_image=garment_im,
                category=cat_hint if cat_hint is not None else 0,
            )
            jpeg = _pil_to_jpeg_bytes(result_im)
            return Response(
                content=jpeg,
                media_type="image/jpeg",
                headers={
                    "X-VTON-Engine": "ootdiffusion",
                    "X-VTON-Category": str(cat_hint),
                },
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"OOTDiffusion inference failed: {str(e)}",
                },
            )

    # Fallback to stub
    if not VTON_STUB_MODE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "VTON service not available",
            },
        )

    jpeg = _stub_tryon(person_im, garment_im)
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "X-VTON-Engine": "stub-blend",
        },
    )
```

### 步骤8：启动OOTDiffusion服务

```bash
cd vton_inference_service

# 激活OOTDiffusion环境
conda activate ootd

# 设置环境变量
export OOTD_PATH=~/OOTDiffusion
export VTON_STUB_MODE=false
export PORT=8011

# 启动服务
uvicorn main:app --host 0.0.0.0 --port 8011
```

---

## 部署IDM-VTON（备选）

### 步骤1：克隆IDM-VTON仓库

```bash
cd ~
git clone https://github.com/yisol/IDM-VTON.git
cd IDM-VTON
```

### 步骤2：安装依赖

```bash
conda create -n idm python=3.10
conda activate idm

pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```

### 步骤3：下载模型权重

```bash
export HF_ENDPOINT=https://hf-mirror.com

python -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='yisol/IDM-VTON', local_dir='./checkpoints')
"
```

### 步骤4：测试IDM-VTON

```bash
python inference.py \
  --cloth_path ./example/cloth/00055_00.jpg \
  --model_path ./example/model/00008_00.jpg \
  --category upper_body
```

**category参数：**
- `upper_body`: 上装
- `lower_body`: 下装
- `dresses`: 裙装

### 步骤5：集成到VTON服务

类似OOTDiffusion的集成方式，创建 `idm_engine.py` 并修改 `main.py`。

---

## 配置主应用

### 完整配置示例

编辑 `backend/.env`：

```env
# ========================================
# VTON服务配置
# ========================================

# 远程VTON服务URL
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon

# VTON服务超时（秒）
VTON_INFERENCE_TIMEOUT_SECONDS=120

# 可选：API密钥
# VTON_INFERENCE_API_KEY=your-shared-secret

# ========================================
# 禁用其他试衣方式
# ========================================

# 禁用百炼（不支持参考图）
DASHSCOPE_TRYON_ENABLED=false

# 禁用本地diffusion兜底
TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=false

# ========================================
# 虚拟试衣v2配置
# ========================================

# 启用虚拟试衣v2
TRYON_V2_ENABLED=true

# 默认使用严格身份保护
TRYON_V2_STRICT_IDENTITY=true
```

### 重启主应用

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

---

## 测试验证

### 1. 测试VTON服务健康检查

```bash
curl http://127.0.0.1:8011/health
```

**预期输出：**
```json
{
  "status": "ok",
  "stub_mode": false,
  "note": "Set VTON_STUB_MODE=false when wiring real OOTDiffusion/IDM inference"
}
```

### 2. 测试VTON服务推理

```bash
curl -X POST http://127.0.0.1:8011/v1/tryon \
  -F "garment_file=@/path/to/garment.jpg" \
  -F "person_file=@/path/to/person.jpg" \
  -F "garment_category=上装" \
  -F "model_gender=neutral" \
  --output result.jpg
```

### 3. 测试主应用集成

1. 打开Flutter应用
2. 进入虚拟试衣页面
3. 上传人物照片和商品图
4. 选择"真实贴身"模式
5. 点击"开始试衣"

**检查结果：**
- ✅ 人物的脸应该与原照片一致
- ✅ 衣服颜色应该与商品图一致
- ✅ 衣服款式应该与商品图一致

### 4. 查看日志

**VTON服务日志：**
```
INFO:     Started server process
INFO:     Waiting for application startup.
OOTDEngine initialized on cuda
INFO:     Application startup complete.
```

**主应用日志：**
```
INFO: VTON remote client: calling http://127.0.0.1:8011/v1/tryon
INFO: VTON remote client: success, received image/jpeg
```

---

## 故障排除

### 问题1：CUDA out of memory

**症状：**
```
RuntimeError: CUDA out of memory
```

**解决方案：**
1. 降低图像分辨率
2. 减少batch size
3. 使用fp16精度
4. 升级GPU

### 问题2：OOTDiffusion导入失败

**症状：**
```
ImportError: No module named 'run.run_ootd'
```

**解决方案：**
```bash
export OOTD_PATH=~/OOTDiffusion
export PYTHONPATH=$OOTD_PATH:$PYTHONPATH
```

### 问题3：模型权重下载失败

**症状：**
```
HTTPError: 403 Forbidden
```

**解决方案：**
```bash
# 使用Hugging Face镜像
export HF_ENDPOINT=https://hf-mirror.com

# 或手动下载
# 访问 https://huggingface.co/levihsu/OOTDiffusion
# 下载所有文件到 ~/OOTDiffusion/checkpoints/
```

### 问题4：推理速度慢

**症状：**
单张图片推理超过30秒

**解决方案：**
1. 确认使用GPU：`torch.cuda.is_available()` 应返回 `True`
2. 减少推理步数：`num_inference_steps=10`（默认20）
3. 使用更快的调度器
4. 升级GPU

### 问题5：结果质量不佳

**症状：**
生成的图像质量差或不符合预期

**解决方案：**
1. 确保输入图像质量高（分辨率、清晰度）
2. 调整推理参数：
   - `num_inference_steps`: 增加到30-50
   - `guidance_scale`: 调整到1.5-3.0
3. 使用正确的category参数
4. 确保人物图是全身照

---

## 性能优化

### 1. 使用GPU加速

确保安装了正确的CUDA版本和PyTorch：

```bash
python -c "import torch; print(torch.cuda.is_available())"
# 应该输出: True
```

### 2. 批量推理

如果需要处理多个请求，可以实现批量推理：

```python
def infer_batch(
    person_images: list[Image.Image],
    garment_images: list[Image.Image],
    categories: list[int],
) -> list[Image.Image]:
    # 批量推理逻辑
    pass
```

### 3. 模型缓存

OOTDEngine使用单例模式，避免重复加载模型：

```python
_engine: Optional[OOTDEngine] = None

def get_engine() -> OOTDEngine:
    global _engine
    if _engine is None:
        _engine = OOTDEngine()
    return _engine
```

### 4. 异步处理

使用FastAPI的后台任务处理长时间推理：

```python
from fastapi import BackgroundTasks

@app.post("/v1/tryon/async")
async def tryon_async(
    background_tasks: BackgroundTasks,
    ...
):
    task_id = generate_task_id()
    background_tasks.add_task(process_tryon, task_id, ...)
    return {"task_id": task_id, "status": "processing"}
```

---

## Docker部署（可选）

### Dockerfile示例

```dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 安装Python
RUN apt-get update && apt-get install -y python3.10 python3-pip git

# 克隆OOTDiffusion
WORKDIR /app
RUN git clone https://github.com/levihsu/OOTDiffusion.git

# 安装依赖
WORKDIR /app/OOTDiffusion
RUN pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu118
RUN pip3 install -r requirements.txt

# 下载模型权重
RUN python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='levihsu/OOTDiffusion', local_dir='./checkpoints')"

# 复制VTON服务代码
WORKDIR /app/vton_service
COPY vton_inference_service/ .
RUN pip3 install -r requirements.txt

# 设置环境变量
ENV OOTD_PATH=/app/OOTDiffusion
ENV VTON_STUB_MODE=false
ENV PORT=8011

# 暴露端口
EXPOSE 8011

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011"]
```

### 构建和运行

```bash
# 构建镜像
docker build -t vton-service:latest .

# 运行容器
docker run --gpus all -p 8011:8011 vton-service:latest
```

---

## 生产部署建议

### 1. 使用进程管理器

使用 `systemd` 或 `supervisor` 管理VTON服务：

```ini
# /etc/systemd/system/vton-service.service
[Unit]
Description=VTON Inference Service
After=network.target

[Service]
Type=simple
User=vton
WorkingDirectory=/home/vton/vton_inference_service
Environment="OOTD_PATH=/home/vton/OOTDiffusion"
Environment="VTON_STUB_MODE=false"
Environment="PORT=8011"
ExecStart=/home/vton/.conda/envs/ootd/bin/uvicorn main:app --host 0.0.0.0 --port 8011
Restart=always

[Install]
WantedBy=multi-user.target
```

### 2. 使用Nginx反向代理

```nginx
upstream vton_service {
    server 127.0.0.1:8011;
}

server {
    listen 80;
    server_name vton.example.com;

    location /v1/tryon {
        proxy_pass http://vton_service;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        client_max_body_size 20M;
    }
}
```

### 3. 监控和日志

使用 Prometheus + Grafana 监控服务性能：

```python
from prometheus_client import Counter, Histogram

tryon_requests = Counter('vton_requests_total', 'Total VTON requests')
tryon_duration = Histogram('vton_duration_seconds', 'VTON inference duration')

@app.post("/v1/tryon")
async def tryon_v1(...):
    tryon_requests.inc()
    with tryon_duration.time():
        # 推理逻辑
        pass
```

---

## 总结

### 部署选项对比

| 方案 | 效果 | 速度 | 部署难度 | 成本 |
|------|------|------|---------|------|
| Stub模式 | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 免费 |
| OOTDiffusion | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | GPU |
| IDM-VTON | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | GPU |
| 百炼API | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 按量付费 |

### 推荐配置

**开发环境：**
- 使用Stub模式快速验证
- 或使用百炼API（如果可以接受效果限制）

**生产环境：**
- 使用OOTDiffusion获得最佳效果
- 部署在独立GPU服务器
- 使用Nginx反向代理
- 配置监控和日志

---

**文档版本**: 1.0
**最后更新**: 2026-04-22
**维护者**: Smart Outfit Assistant Team
