# 虚拟试衣 / 专用 VTON 交付说明（2026-04）

本文档记录本仓库在 **2026 年 4 月**围绕「照片级试衣、百炼可选接入、独立 VTON 服务契约」已落地的实现，便于审计与 onboarding。详细选型与 PoC 步骤仍以 [`VTON_INTEGRATION.md`](VTON_INTEGRATION.md) 为准。

## 已实现能力

### 后端 `POST /api/v1/tryon/garment`

- **推理优先级**（由高到低）：
  1. **阿里云百炼（DashScope）**：`DASHSCOPE_TRYON_ENABLED=true` 且配置 `DASHSCOPE_API_KEY` 时优先调用 [`bailian_tryon_client.py`](../backend/app/services/bailian_tryon_client.py)。
  2. **专用远程 VTON**：`VTON_INFERENCE_URL` 指向独立 GPU 服务（multipart 契约见 [`vton_remote_client.py`](../backend/app/services/vton_remote_client.py)）。
  3. **本机管线**：[`virtual_tryon.py`](../backend/app/services/virtual_tryon.py)（diffusers inpainting，失败则去背景 + 粘贴 fallback）。

- **百炼失败时的回退**：默认 `DASHSCOPE_TRYON_FALLBACK_LOCAL=true` 时，百炼失败后继续尝试远程 VTON 与本机管线（与 `VTON_INTEGRATION.md` 一致）。

- **Windows JPEG 保存**：试衣结果在编码为 JPEG 时，通过**临时文件**写出再读回字节，避免在部分 Windows / Pillow 版本下对 `BytesIO` 调用 JPEG 保存路径触发异常（此前可导致扩散成功但接口 500）。

### 独立推理 Stub / 示例服务

- [`vton_inference_service/`](../vton_inference_service/)：最小 FastAPI，对齐 `POST /v1/tryon` 与主 API 的 multipart 字段；默认 Stub 便于联调，可按目录 `README.md` 替换为真实 OOTDiffusion 等推理。

### 运维与文档

- 示例 Compose：[`deploy/vton/docker-compose.vton-example.yml`](../deploy/vton/docker-compose.vton-example.yml)。
- PoC 记录模板：[`scripts/vton_poc/POC_RUNBOOK.md`](../scripts/vton_poc/POC_RUNBOOK.md)。
- 环境变量说明：[`backend/.env.example`](../backend/.env.example) 中的 `VTON_*`、`DASHSCOPE_*`。

### Flutter 虚拟试衣页

- **单次 HTTP 请求**生成一张结果图（轮播组件仍兼容单张展示）。
- **品类**：可选 `上装` / `下装` / `裙装` / 自动，对应表单 `garment_category`，用于百炼与专用 VTON 路由；页面文案提示全身图、连衣裙与下装互斥等，降低错配。

## CatVTON VRAM 优化（2026-04 补充）

本地 CatVTON 支持以下极限 VRAM 优化，适合 8GB 及以下显存（RTX 4060 Laptop 等）：

| 开关 | 说明 | 推荐值 |
|------|------|--------|
| `CATVTON_LOW_VRAM_MODE=true` | 一键低显存模式（等于 force_fp16 + vae_slicing + xformers） | RTX 4060 Laptop |
| `CATVTON_FORCE_FP16=true` | 强制 fp16（节省约 2GB 显存） | RTX 4060 Laptop |
| `CATVTON_ENABLE_VAE_SLICING=true` | VAE 分片推理（峰值显存 -40%） | 全系列 |
| `CATVTON_ENABLE_XFORMERS=true` | xformers 高效注意力 | 全系列 |

详细说明与快速测试命令见 [`VTON_INTEGRATION.md`](VTON_INTEGRATION.md)。

快速测试（无需后端，先验证 mask）：
```bash
cd backend && python scripts/test_catvton_direct.py --preprocess-only
cd backend && python scripts/test_catvton_direct.py --low-vram
```
