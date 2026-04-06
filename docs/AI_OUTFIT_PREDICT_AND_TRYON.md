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

### 响应体（JSON）

| 字段 | 说明 |
|------|------|
| `score` | 模型输出的风格分（浮点） |
| `recommendations` | `{ "outfit": string, "score": number }[]`，Top3 |
| `explanation` | 中文短解释 |

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

### Fallback（未加载或未使用扩散模型时）

历史上曾使用 **`Image.blend` 半透明叠图**，易与「含模特的商品图」叠加出 **双人脸 / 重影**。

当前逻辑（`backend/app/services/virtual_tryon.py`）：

1. **衣服图人脸检测**（OpenCV Haar）：若检测到正面人脸 → 返回 **400**，提示上传无模特白底图。
2. **去背景**：优先 **`rembg`**（可选 `pip install rembg`），否则用亮度/饱和度阈值生成 mask 作 alpha。
3. **合成**：**mask + `paste`**，不再使用全图 `Image.blend`。

### Flutter 客户端

- 单次请求超时默认较长（虚拟试衣 CPU 推理慢），见 `ApiClient.virtualTryon`。
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
