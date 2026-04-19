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

## 相关文档索引

| 主题 | 文档 |
|------|------|
| OOTDiffusion vs IDM-VTON、契约、Docker 示例 | [`VTON_INTEGRATION.md`](VTON_INTEGRATION.md) |
| `/predict`、Vite、试衣 API 细节 | [`AI_OUTFIT_PREDICT_AND_TRYON.md`](AI_OUTFIT_PREDICT_AND_TRYON.md) |
| PyTorch CUDA（Windows） | [`PYTORCH_CUDA_WINDOWS.md`](PYTORCH_CUDA_WINDOWS.md) |
