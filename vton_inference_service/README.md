# VTON 独立推理服务（最小 HTTP）

与主应用 [`backend/app/services/vton_remote_client.py`](../backend/app/services/vton_remote_client.py) 的 **multipart 契约**一致，支持三种运行模式：

- **CatVTON 模式**（默认生产选项）：直接调用本地 `catvton_runner.py` subprocess，GPU 利用率高，无需独立服务进程；支持 MediaPipe PoseLandmarker 自动掩码
- **HTTP 服务模式**：另一进程或 Docker（`--gpus all`），用于需要网络调用的场景
- **Stub 演示模式**：`VTON_STUB_MODE=true`，返回轻量叠图（非真实推理，仅用于流水线演示）

## 运行（独立 venv，推荐）

```powershell
cd vton_inference_service
python -m venv .venv
..\.venv\Scripts\activate   # 若从仓库根使用已有 .venv 也可，但长期建议本目录独立 venv
pip install -r requirements.txt

# 方式一：CatVTON 模式（推荐，无需独立 GPU 服务进程）
set CATVTON_PATH=D:\path\to\CatVTON
set VTON_STUB_MODE=false
set VTON_ENGINE=catvton
set PORT=8011
uvicorn main:app --host 0.0.0.0 --port 8011

# 方式二：Stub 演示模式
set VTON_STUB_MODE=true
set PORT=8011
uvicorn main:app --host 0.0.0.0 --port 8011
```

主应用 `.env`（以 CatVTON 模式为例）：

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
| `VTON_STUB_MODE` | `true`（默认 Stub）：返回叠图 JPEG；`false`：调用真实推理（CatVTON / OOTDiffusion） |
| `VTON_ENGINE` | `catvton`（默认）或 `ootdiffusion`；控制 Stub=false 时的推理后端 |
| `CATVTON_PATH` | CatVTON 仓库目录（含权重或首次自动下载） |
| `VTON_SERVICE_API_KEY` | 非空则要求 Bearer 与之一致 |
| `PORT` | 监听端口（由 uvicorn 命令行指定即可） |
| `CATVTON_WIDTH`、`CATVTON_HEIGHT`、`CATVTON_STEPS`、`CATVTON_GUIDANCE` | CatVTON 推理参数 |

## CatVTON 子进程推理（推荐）

CatVTON 无需独立 GPU 服务进程。`main.py` 在 `VTON_ENGINE=catvton` 时，调用同目录 `catvton_runner.py` subprocess（隔离 Python 环境依赖），后者通过 MediaPipe PoseLandmarker 生成人体掩码，驱动 CatVTONPipeline 完成试衣，返回 JPEG 结果。

## 接入真实 OOTDiffusion / IDM-VTON

1. 在 **另一 venv** 按官方 README 安装 GPU 依赖与权重（见 [`scripts/vton_poc/POC_RUNBOOK.md`](../scripts/vton_poc/POC_RUNBOOK.md)）。
2. 在本服务 `main.py` 的 `tryon_v1` 中，将 `VTON_STUB_MODE` 分支替换为对上游 `inference` 的调用；**品类**可用表单 `garment_category` 映射到 OOTDiffusion 的 `0/1/2` 或 IDM 的 `upper_body` / `lower_body` / `dresses`（以所选脚本为准）。
3. 成功推理后仍返回 **JPEG 字节**（`Response(content=..., media_type="image/jpeg")`）或 JSON `result_image_base64`，与主客户端兼容。

## License

本目录代码为项目内 MIT/仓库许可；**CatVTON / OOTDiffusion / IDM-VTON 权重与上游代码**仍受各自 **CC BY-NC-SA** 等约束，商用需自行合规。
