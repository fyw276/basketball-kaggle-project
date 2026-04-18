# AI 穿搭打分、Vite 演示前端与虚拟试衣（2026）

本文档记录 **统一 `/predict` 接口**、**React/Vite 演示页**、**Flutter 侧调用约定** 与 **虚拟试衣 fallback 防重影** 的实现要点，便于与旧文档或口头约定对齐。

## 1. 穿搭风格分 `POST /predict`

### 行为

- **同一套模型与响应结构** 在以下两处等价可用：
  - 独立进程：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765`（见 [`scripts/run_predict_api.ps1`](../scripts/run_predict_api.ps1)）
  - 主应用：`python -m uvicorn app.main:app`（默认端口见 `backend/.env` 的 `PORT`，常为 **8010**）
    路由为 **`POST /predict`**（**无** `/api/v1` 前缀）。

### 请求体（JSON）

`top`, `bottom`, `color_top`, `color_bottom`, `season`, `occasion`（均为字符串）。

请求示例（可直接复制）：

```bash
curl -X POST "http://127.0.0.1:8010/predict" \
  -H "Content-Type: application/json" \
  -d '{
    "top": "衬衫",
    "bottom": "牛仔裤",
    "color_top": "白色",
    "color_bottom": "蓝色",
    "season": "春季",
    "occasion": "通勤"
  }'
```

### 响应体（JSON）

| 字段 | 说明 |
|------|------|
| `score` | 模型输出的风格分（浮点） |
| `recommendations` | `{ "outfit": string, "score": number }[]`，Top3 |
| `explanation` | 中文短解释 |
| `source` | 结果来源：`local`（仅本地）/ `hybrid`（本地+外部增强） |
| `fallback_reason` | 触发或回退原因：`low_confidence` / `small_margin` / `external_failed` / `null` |
| `model_version_local` | 本地模型版本标识 |
| `model_version_external` | 外部增强模型版本标识（未调用时为 `null`） |
| `latency_ms` | 当前请求推理耗时（毫秒） |

响应示例（本地模式）：

```json
{
  "score": 8.4,
  "recommendations": [
    { "outfit": "衬衫 + 牛仔裤", "score": 8.4 },
    { "outfit": "Shirt + Chinos", "score": 8.1 },
    { "outfit": "Hoodie + Joggers", "score": 7.8 }
  ],
  "explanation": "颜色搭配协调，适合当前季节和场景",
  "source": "local",
  "fallback_reason": null,
  "model_version_local": "local-sklearn-pipeline",
  "model_version_external": null,
  "latency_ms": 42
}
```

响应示例（双通道增强）：

```json
{
  "score": 7.9,
  "recommendations": [
    { "outfit": "衬衫 + 牛仔裤", "score": 7.9 },
    { "outfit": "Shirt + Chinos", "score": 7.6 },
    { "outfit": "Hoodie + Joggers", "score": 7.3 }
  ],
  "explanation": "外部增强判定更匹配",
  "source": "hybrid",
  "fallback_reason": "low_confidence",
  "model_version_local": "local-sklearn-pipeline",
  "model_version_external": "ext-v1",
  "latency_ms": 165
}
```

实现逻辑位于 `backend/app/services/outfit_style_predict.py`（主应用挂载 `backend/app/api/predict_style.py`）。

### Flutter 与主后端同进程

若只跑 **`app.main`**，希望 Flutter 的预测请求也打到同一端口：

```bash
cd mobile
flutter run --dart-define=PREDICT_API_PORT=8010
```

默认 **`PREDICT_API_PORT=8765`** 对应独立 predict 服务；与 **`API_PORT`**（主 API，默认 8010）是两套端口，请勿混用。

---

## 2. Vite 演示前端（`frontend/`）

- 技术栈：**Vite + React**。
- 环境变量：`VITE_API_BASE` 指向 predict 服务根 URL（无尾斜杠），例如 `http://127.0.0.1:8765`。
- 调用：`frontend/src/api/aiScore.js` → `POST .../predict`，展示评分、推荐列表与解释（见 `ResultCard` 等）。

详见 [`frontend/README.md`](../frontend/README.md)。

---

## 3. 虚拟试衣（`/api/v1/tryon/garment`）

### 认证

需 JWT（`Authorization: Bearer`），与主 API 一致。

### 请求（`multipart/form-data`）

| 字段 | 必填 | 说明 |
|------|------|------|
| `garment_file` | 是 | 商品/衣物照片 |
| `person_file` | 是 | 人物照片 |
| `prompt` | 否 | 文本提示（扩散路径会使用） |
| `model_gender` | 否 | `male` / `female` / `neutral`（默认 `neutral`） |
| `garment_category` | 否 | 衣橱品类中文，如 `下装(汉)`、`长裤`；**fallback 粘贴**时用于下装/上装锚点与上半身 alpha 裁切，改善「整块裤子盖住上衣」 |

### 扩散模型路径（diffusers）

- **懒加载**：进程启动**不会**立即加载 SD；**首次**命中试衣接口时才 `from_pretrained`（成功后在单例内缓存）。
- **默认模型**：`stable-diffusion-v1-5/stable-diffusion-inpainting`（见 `virtual_tryon.py` / `SD_VTON_MODEL_ID`）；需本机已安装 `diffusers`、`accelerate`、`torch`、`torchvision`、`transformers`，且能访问 HF 或已缓存权重（见下文 `TRYON_MODEL_LOCAL_PATH` / `HF_*`）。
- **PyTorch 版本**：`requirements.txt` 要求 **`torch>=2.6`**（`.bin` 权重与 CVE 相关限制）。**`torchvision` 必须与 `torch` 同一代**（例如同一轮 `pip install torch torchvision`）。常见故障：只升级 `torch` 未升级 `torchvision` → `CLIPImageProcessor` 导入失败或 `operator torchvision::nms does not exist` → 加载管线失败并长期走 fallback。
- **勿误开** `TRYON_FORCE_FALLBACK=true`：该开关会**故意跳过**扩散加载，只保留粘贴合成；仅在网络/机器无法承载大模型时临时使用。

### Fallback（未加载或未使用扩散模型时）

历史上曾使用 **`Image.blend` 半透明叠图**，易与「含模特的商品图」叠加出 **双人脸 / 重影**。

当前逻辑（`backend/app/services/virtual_tryon.py`）：

1. **衣服图人脸检测**（OpenCV Haar）：若检测到正面人脸 → 返回 **400**，提示上传无模特白底图。
2. **去背景**：优先 **`rembg`**（可选 `pip install rembg`），否则用亮度/饱和度阈值生成 mask 作 alpha。
3. **合成**：**mask + `paste`**，不再使用全图 `Image.blend`。
4. **品类提示**：若提供 `garment_category`，会映射为「上装 / 下装」等区域，并对**下装**在人物高度约 42% 以上清除 overlay alpha，减少盖住原有上衣；`连衣裙` 等整身类不会误标为纯下装。

### 本地模型目录（避免校园网/HF 缓存问题）

虚拟试衣现支持优先从本地目录加载 diffusers 模型。当前默认公开模型已切换为
`stable-diffusion-v1-5/stable-diffusion-inpainting`。若你已手动把它下载到本机，
可在 `backend/.env` 中配置：

```env
TRYON_MODEL_LOCAL_PATH=D:\models\stable-diffusion-inpainting
```

配置后，`virtual_tryon.py` 会优先从该目录执行 `StableDiffusionInpaintPipeline.from_pretrained(...)`，
不再依赖 Hugging Face cache 目录结构。若本地目录不存在，则自动回退到原先的 HF 模型 ID 路径。

若你当前只想先把功能跑通，而不希望请求时阻塞在 Hugging Face 下载，可在 `backend/.env`
中临时开启：

```env
TRYON_FORCE_FALLBACK=true
```

开启后，后端会直接跳过 diffusers / HF 模型加载，立即使用现有的本地“去背景 + 粘贴”
fallback 合成链路，适合校园网或未完成模型下载时先验证接口与前端流程。

### 本地启动与端口（Windows）

- 启动命令须在 **`backend`** 目录执行，否则 `ModuleNotFoundError: No module named 'app'`。
- **`WinError 10048`**：8010 已被占用（例如另一个 `uvicorn`），需结束旧进程或换端口；换端口时 Flutter 使用 `--dart-define=API_PORT=<端口>`。

### Flutter 客户端

- 单次请求超时默认较长（虚拟试衣 CPU 推理慢），见 `ApiClient.virtualTryon`。
- 可选参数 **`garmentCategory`**：非空时随 multipart 发送 `garment_category`，与衣橱品类一致时 fallback 效果更好。
- 非 200 响应会解析 JSON 中的 **`detail`**（FastAPI 错误信息）。
- 页面提示：**请上传无模特的衣服图，否则效果会出现重影**。

---

## 4. Flutter Web 根路径白屏

直接打开 **`http://localhost:<port>/`** 时，若路由未注册 **`/`**，可能出现 **整页空白**。

已在 `mobile/lib/main.dart` 增加 **`/` → `/auth`** 的重定向，并配置 `errorBuilder` 兜底。

---

## 5. 与旧文档的差异

- 若某处仍写「predict 仅在 8765」或「主 API 无 `/predict`」——以 **本节第 1 条** 为准：主应用已挂载 **`POST /predict`**。
- 若写「虚拟试衣为半透明叠图」——以 **本节第 3 条** 为准：fallback 已改为 **抠图 + 粘贴**（并拒绝含人脸的衣服图）。
- 若写「试衣仅粘贴、无扩散」——以环境为准：依赖齐全且未设 `TRYON_FORCE_FALLBACK` 时，应能加载 **inpainting**；日志中 **`Using fallback composition mode`** 表示本次仍在 fallback，需对照 **`Failed to load try-on model`** 的完整报错排查（多为 torch/torchvision 不匹配或离线缓存缺失）。
