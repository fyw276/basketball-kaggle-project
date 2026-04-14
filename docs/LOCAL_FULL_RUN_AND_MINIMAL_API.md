# 本地完整运行 + 最小改动 API 接入（执行方案）

本文与仓库实现一致：**不改业务主流程**；外部能力通过 **环境变量** 开关，失败时沿用现有 **fallback**。

---

## A. 本地部署方案（先跑起来）

### 1. 后端（端口 8010）

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
# 若本机未装 PostgreSQL，见下文「本地 SQLite」一行替换 DATABASE_URL
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 2. 本地 SQLite（可选，避免先装 PostgreSQL）

在 `backend/.env` 中将数据库改为单文件（**四斜杠**接绝对路径的规则见 `docs/PRODUCTION_DEPLOY.md`；开发相对路径示例）：

```env
DATABASE_URL=sqlite:///./outfit_local.db
```

### 3. 前端（Flutter Web）

```bash
cd mobile
flutter pub get
flutter run -d chrome
```

默认 API 指向本机 **8010**（与 `kApiPort` 一致）。

### 4. 验证（建议顺序）

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 浏览器打开 `http://127.0.0.1:8010/docs` | Swagger 正常 |
| 2 | `http://127.0.0.1:8010/health` | `healthy` |
| 3 | 前端完成注册 / 登录 | 进入主页 |
| 4 | 衣橱上传图片 | 识别完成、无持续 500 |
| 5 | 智能穿搭：上传参考图 → 生成 | 返回 3 套；天气可先默认或手动城市 |

**CORS**：本地开发保持 `CORS_ALLOW_ALL_LOCALHOST=true`（默认），Flutter Web 随机端口不被拦。

---

## B. API 接入清单（最小必要）

### 重要说明（天气数据来源）

| 能力 | 仓库中的实际来源 |
|------|------------------|
| **默认：气温 + WMO 天气码** | **Open-Meteo**（无需 Key） |
| **可选：实况温度 + 中文天气文案** | **高德天气查询** `v3/weather/weatherInfo`（`extensions=base`），需 **`AMAP_WEATHER_ENABLED=true`** 且 **`AMAP_WEB_KEY`**（与逆地理同一类 Web 服务 Key） |
| **国内省市区街道** | **高德逆地理** + Open-Meteo + Nominatim |
| **补充地理** | Nominatim（OSM） |

启用高德实况时：经纬度场景优先用逆地理返回的 **adcode** 查天气；无 adcode 时用解析出的 **市名**；失败则仍用 Open-Meteo。API 响应中增加 **`weather_source`**：`amap` 或 `open_meteo`。

### 第一步：高德 Key +（可选）高德实况天气

```env
AMAP_WEB_KEY=你的高德_Key
# 为 true 时，温度与「晴/多云/…」文案优先高德，失败回退 Open-Meteo
AMAP_WEATHER_ENABLED=true
```

确保本机可访问公网 **Open-Meteo** 与 **Nominatim**（作回退）；高德接口需能访问 `restapi.amap.com`。

### 第二步：大模型（智能穿搭卡片解释等）

项目使用 **OpenAI 兼容** `POST .../chat/completions`（见 `AI_RECOMMENDER_*`）。在 `.env` 中：

```env
AI_RECOMMENDER_ENABLED=true
AI_RECOMMENDER_API_BASE_URL=<厂商提供的 compatible-mode 基址，以 /v1 结尾>
AI_RECOMMENDER_API_KEY=<你的 Key>
AI_RECOMMENDER_MODEL=<模型名，以控制台为准>
AI_RECOMMENDER_TIMEOUT_MS=8000
```

**通义千问**：在阿里云控制台开启 **OpenAI 兼容**，使用控制台给出的 **base URL**（常见为 DashScope 兼容地址，以文档为准）。
**豆包**：火山方舟 **OpenAI 兼容** 端点 + 模型 endpoint id（以控制台为准）。

关闭 LLM 时设 `AI_RECOMMENDER_ENABLED=false`，逻辑回退到模板文案，**主流程不变**。

### 第三步（可选）：OSS / 云存储

默认 **`UPLOAD_DIR` 本地磁盘**。多机或公网持久化需接 **S3 兼容 / 阿里云 OSS**，需扩展 `StorageService`，**超出「只改配置」**，列为后续评估项。

---

## C. 接入顺序（建议）

1. **先跑通 A**：后端 +（可选 SQLite）+ Flutter，无额外 Key。
2. **仅加环境变量**：`AMAP_WEB_KEY` → 再按需 `AI_RECOMMENDER_*`。
3. **勿先上 OSS**，除非已有多实例或磁盘不持久问题。

---

## D. 不改动原有功能的最小接入

- **保留**：本地 CLIP、衣橱、推荐引擎、上传、`EXTERNAL_ENHANCE_ENABLED=false` 时 `/predict` 纯本地。
- **仅配置**：高德 Key、LLM 开关与 URL。
- **失败策略**：天气/逆地理失败已有默认与 Snackbar 提示；LLM 失败走 `_generate_ai_recommendation` 内模板 fallback。

---

## E. 验收标准（可直接对照）

- [ ] 登录、衣橱、相似度、适合度、智能穿搭、情绪穿搭、虚拟试衣均可**在 UI 点通**（试衣无 GPU 时可能为合成 fallback，属预期）。
- [ ] 智能穿搭：在已配置 `AMAP_WEB_KEY` 且网络可达时，**地址与天气可自动解析**；否则为默认/手动路径。
- [ ] 无静态资源 **404**（Flutter Web 构建页由 `flutter run` 提供）、后端无**持续** 500、浏览器无 **CORS** 阻断。
- [ ] 提交前：`pre-commit run --all-files`，`pytest tests_lite tests/test_release_and_observability.py`，`flutter test`（与仓库钩子一致）。

---

## 相关文档

- [QUICK_START.md](../QUICK_START.md)
- [WEATHER_DISPLAY_AND_HF_ENV.md](WEATHER_DISPLAY_AND_HF_ENV.md)
- [OPS_RELEASE_AND_OBSERVABILITY.md](OPS_RELEASE_AND_OBSERVABILITY.md)
- [PRODUCTION_DEPLOY.md](PRODUCTION_DEPLOY.md)
