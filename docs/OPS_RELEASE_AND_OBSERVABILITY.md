# 发布台账与外部依赖观测

本文描述后端 **发布工件版本台账**、**环境快照**（无密钥）与 **天气 / 试衣 / AI / 混合外部增强** 的进程内指标看板；与 `deploy/ecs/RELEASE_MANIFEST.example` 及部署脚本对齐。

## 1. 发布台账 `GET /release`

公开接口（无需登录），返回 JSON（经统一 Envelope 包装时，业务体在 `data` 内）：

- **`ledger`**
  - `frontend_index_sha256`：Flutter Web 等前端构建指纹（如 `main.dart.js` 或整包 SHA256），由 CD 写入。
  - `backend_git_commit`：运行中后端对应的 Git commit。
  - `deploy_time_utc`：部署时间（UTC，ISO 字符串）。
  - `manifest_path_configured` / `manifest_loaded`：是否配置了 `RELEASE_MANIFEST_PATH` 且成功解析 JSON。
- **`env_snapshot`**：非敏感运行配置（`ENVIRONMENT`、`APP_VERSION`、混合推理与 AI 开关/超时、是否配置 AMap/HF、限流等），**不含**数据库 URL、密钥。

### 注入方式（`backend/app/core/config.py`）

| 变量 | 含义 |
|------|------|
| `RELEASE_MANIFEST_PATH` | 可选。指向服务器上的 JSON 文件。 |
| `RELEASE_FRONTEND_INDEX_SHA256` | 覆盖/补充 manifest 中的前端指纹。 |
| `RELEASE_BACKEND_GIT_COMMIT` | 覆盖/补充后端 commit。 |
| `RELEASE_DEPLOY_TIME_UTC` | 覆盖/补充部署时间。 |

Manifest JSON 可使用的键（与示例文件兼容）：`frontend_index_sha256`、`backend_git_commit`、`deploy_time_utc`；也兼容旧键名 `WEB_BUILD_SHA256`、`SOURCE_GIT_COMMIT`、`DEPLOY_TIME_UTC`。

部署脚本或 systemd `EnvironmentFile` 在发版后写入上述变量或文件，即可在公网 `curl https://<域>/release` 验收「前后端是否同批次」。

## 2. 存活 / 就绪（与 Nginx）

- `GET /health`：存活。
- `GET /health/ready`：就绪（含数据库探测）。

生产环境若 Nginx 对 `/` 使用 `try_files ... /index.html`，**必须**将 `/health`、`/health/ready`、`/release` 反代到 Uvicorn，否则浏览器/探针会得到 HTML 而非 JSON。示例见 `deploy/ecs/nginx-api-locations.conf` 与 `docs/PRODUCTION_DEPLOY.md`。

## 3. 依赖观测 JSON `GET /api/v1/analytics/dependency-observability`

需登录（Bearer），返回各 **domain** 的计数与占比（自 **当前进程** 启动以来累计）：

| domain | 含义 |
|--------|------|
| `weather` | 智能穿搭天气 API：成功；逆地理兜底记 **degraded**；异常记 failure/timeout。 |
| `tryon` | 虚拟试衣：`success` / `fallback`→degraded /错误→failure等。 |
| `ai` | 智能穿搭 OpenAI 兼容解释层：成功解析；解析降级；超时/其它错误。 |
| `external_enhance` | 混合推理 `call_external_enhance`：成功；不可用类 RuntimeError→degraded；其它→failure/timeout。 |

每项含 `counts`（success/failure/timeout/degraded）、`total`、以及各 `*_rate`（有样本时）。

**限制**：多 worker 时各进程独立计数；全局 SLO 需在网关或 Prometheus 侧聚合，或配合单 worker / 共享存储扩展。

## 4. HTML 看板 `GET /ops/dependency-board`

- 默认 **404**。
- 设置 **`OPS_DASHBOARD_ENABLED=true`** 后返回简易 HTML 表（同域指标 + 内嵌 `/release` 摘要 JSON）。
- **必须**仅在内网或 IP 白名单后暴露，不可对公网裸开。

## 5. 与混合推理文档的关系

外部增强调用链与配置见 [HYBRID_INFERENCE_FAST_TRACK.md](HYBRID_INFERENCE_FAST_TRACK.md)；`external_enhance` 指标在 `app/services/external_enhance_client.py` 的 `call_external_enhance` 内统一打点。

## 6. 相关测试

- `backend/tests/test_release_and_observability.py`：台账、鉴权、看板开关、外部增强 degraded 计数。
- 预推送钩子：与 `tests_lite` 一并运行（见仓库根 `.pre-commit-config.yaml`）。
