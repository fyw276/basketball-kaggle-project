# VTON 独立推理服务（最小 HTTP）

与主应用 [`backend/app/services/vton_remote_client.py`](../backend/app/services/vton_remote_client.py) 的 **multipart 契约**一致，用于：

- 本地 **端到端联调**（默认 **Stub**：轻量叠图，非真实 OOTDiffusion/IDM）；
- 后续将 `main.py` 中 Stub 分支替换为 **OOTDiffusion** 或 **IDM-VTON** 官方推理调用。

## 运行（独立 venv，推荐）

```powershell
cd vton_inference_service
python -m venv .venv
..\.venv\Scripts\activate   # 若从仓库根使用已有 .venv 也可，但长期建议本目录独立 venv
pip install -r requirements.txt
set VTON_STUB_MODE=true
set PORT=8011
uvicorn main:app --host 0.0.0.0 --port 8011
```

主应用 `.env`：

```env
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon
# 可选：与服务端一致时校验
# VTON_INFERENCE_API_KEY=your-shared-secret
# VTON_SERVICE_API_KEY=your-shared-secret
```

若设置 `VTON_SERVICE_API_KEY`，请求须带 `Authorization: Bearer <同值>`（与主应用 `VTON_INFERENCE_API_KEY` 对齐）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `VTON_STUB_MODE` | `true`（默认）：返回 Stub 叠图 JPEG；`false`：未接真实推理时返回 503 JSON |
| `VTON_SERVICE_API_KEY` | 非空则要求 Bearer 与之一致 |
| `PORT` | 监听端口（由 uvicorn 命令行指定即可） |

## 接入真实 OOTDiffusion / IDM-VTON

1. 在 **另一 venv** 按官方 README 安装 GPU 依赖与权重（见 [`scripts/vton_poc/POC_RUNBOOK.md`](../scripts/vton_poc/POC_RUNBOOK.md)）。
2. 在本服务 `main.py` 的 `tryon_v1` 中，将 `VTON_STUB_MODE` 分支替换为对上游 `inference` 的调用；**品类**可用表单 `garment_category` 映射到 OOTDiffusion 的 `0/1/2` 或 IDM 的 `upper_body` / `lower_body` / `dresses`（以所选脚本为准）。
3. 成功推理后仍返回 **JPEG 字节**（`Response(content=..., media_type="image/jpeg")`）或 JSON `result_image_base64`，与主客户端兼容。

## License

本目录代码为项目内 MIT/仓库许可；**OOTDiffusion / IDM-VTON 权重与上游代码**仍受各自 **CC BY-NC-SA** 等约束，商用需自行合规。
