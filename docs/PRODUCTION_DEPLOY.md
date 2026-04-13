# 生产部署清单（阿里云 ECS / Nginx）

面向「Flutter Web 同源 + FastAPI 反代」的典型架构。完成下列项可显著减少「本地正常、公网异常」与数据丢失。

## 1. 环境与密钥（P0）

- `ENVIRONMENT=production`，`DEBUG=False`
- `JWT_SECRET_KEY`：至少32 字节随机串；**禁止**保留仓库默认值（启动日志会 `CRITICAL` 提示）
- `CORS_ORIGINS` 或 `CORS_ALLOW_PATTERN`：填写实际前端域名（含 `https://`），与浏览器 **Origin** 完全一致
- 数据库：`DATABASE_URL` 指向生产实例（PostgreSQL 等），与本地 SQLite 分离

## 2. Nginx 反代（P0）

浏览器只应访问 **80/443**；需把 API 与静态资源转到后端。

检查项：

- `location /api/v1/` → `proxy_pass http://127.0.0.1:8010/api/v1/`（或等价 upstream）
- `location /predict` → 同一后端（`POST /predict` 无 `/api/v1` 前缀）
- `location /uploads/` → 与后端 `UPLOAD_DIR` 一致（或反代到 `http://127.0.0.1:8010/uploads/`）
- **`/health`、`/health/ready`、`/release`** → 必须反代到后端；若仅用 `try_files ... /index.html` 承接 `/`，探针访问 `/health` 会得到 **HTML** 而非 JSON（负载均衡健康检查会误判）。可选：`/ops/dependency-board`（仅当 `OPS_DASHBOARD_ENABLED=true` 且内网限制访问时）
- `client_max_body_size` ≥ 上传上限（与 `MAX_UPLOAD_SIZE` 对齐，建议 ≥15m）
- 若 HTTPS 终止在 Nginx，后端可仍用 HTTP；注意 `X-Forwarded-For` / `X-Forwarded-Proto`（限流与日志会用到）

示例片段（按需改域名与端口）：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example.com;

    root /usr/share/nginx/html;
    index index.html;

    location /api/v1/ {
        proxy_pass http://127.0.0.1:8010/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 20m;
    }

    location /predict {
        proxy_pass http://127.0.0.1:8010/predict;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 4m;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8010/uploads/;
        proxy_set_header Host $host;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8010/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location = /health/ready {
        proxy_pass http://127.0.0.1:8010/health/ready;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location = /release {
        proxy_pass http://127.0.0.1:8010/release;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

验收：

```bash
curl -fsS https://your-domain/health
curl -fsS https://your-domain/health/ready
curl -fsS https://your-domain/release
```

发布台账与依赖指标说明见 [OPS_RELEASE_AND_OBSERVABILITY.md](OPS_RELEASE_AND_OBSERVABILITY.md)；可直接复用仓库内 **`deploy/ecs/nginx-api-locations.conf`** 片段。

## 3. 持久化（P0）— 账户照片「永久」不丢

刷新页面后图片没了，通常是 **URL 已404**（文件从未持久化或被发布覆盖），不是前端缓存问题。生产必须满足：

### 3.1 上传目录 `UPLOAD_DIR`（必改）

- **禁止**长期用默认值 `./uploads`：它相对 **进程工作目录**，发版、改 systemd `WorkingDirectory` 或清理目录后，容易写到新位置或旧文件被落在「旧目录」里，表现为「一刷新/重新登录图没了」。
- **必须**改为 **绝对路径**，且放在 **代码与 Tar 解压目录之外**，例如单独云盘或固定目录：

  ```bash
  sudo mkdir -p /var/lib/clothing-assistant/uploads
  ```

- 在 `backend/.env` 中设置（示例）：

  ```env
  UPLOAD_DIR=/var/lib/clothing-assistant/uploads
  ```

- 若 Nginx 用 `alias` 直出静态文件，需与上述物理路径一致；若用 `proxy_pass .../uploads/`，则与 FastAPI 挂载的 `UPLOAD_DIR` 一致即可（见 §2）。

- **从旧路径迁一次**（若已有数据在 `backend/uploads`）：

  ```bash
  sudo rsync -a /opt/clothing-assistant/clothing-assistant-main/backend/uploads/ \
    /var/lib/clothing-assistant/uploads/
  ```

### 3.2 数据库 `DATABASE_URL`

- **推荐** PostgreSQL（RDS/自建），与代码目录完全解耦。
- 若使用 **SQLite**，库文件也必须放在 **独立绝对路径**（不要放在 `backend/` 里，避免被误覆盖），例如：

  ```env
  DATABASE_URL=sqlite:////var/lib/clothing-assistant/data/outfit.db
  ```

  注意：`sqlite:` 后是 **四个** `/` 再接绝对路径（SQLAlchemy 约定）。

### 3.3 可复制模板

仓库内 **[deploy/ecs/env.production.persistent.example](../deploy/ecs/env.production.persistent.example)** 含完整示例；改好后重启 `clothing-backend`。

### 3.4 启动自检

生产环境若仍使用相对 `UPLOAD_DIR` 或 SQLite，应用启动日志会打出 **WARNING**，提示按本文修正。

## 4. 就绪与限流（P1）

- **就绪探针**：`GET /health/ready`（检查数据库）；负载均衡/编排将流量打到就绪实例
- **存活探针**：`GET /health`
- **限流**：`.env` 中 `ENABLE_RATE_LIMIT=true` 且 `RATE_LIMIT_PER_MINUTE=60`（或按需）；多 worker 进程下为**每进程**计数，需网关层限流时请同时在 SLB/WAF 配置

## 5. 与脚本 `deploy_full_to_ecs.ps1` 的配合

- 脚本**不包含** `.env`：首次在服务器创建 `backend/.env` 并按上表填写。
- **部署模式**（详见 [deploy/ecs/README.md](../deploy/ecs/README.md)）：**Tar**（默认，写 `RELEASE_MANIFEST`）或 **Git**（远端完整 clone + `pull`）；SSH 使用 `-IdentityFile` 实现免密（`BatchMode=yes`）。
- **发布后验收**：默认跑 `post_deploy_verify` + `full_chain_consistency_audit`；紧急可加 `-SkipPostDeployVerify`。另建议对公网执行 `curl -fsS https://<域>/release` 核对 `ledger` 与 `env_snapshot`（与 CD 注入的 `RELEASE_*` 或 manifest 一致）。
- Flutter Web 线上默认使用 **当前页 `origin` + `/api/v1`**，依赖上述 Nginx；若需异常架构再使用 `flutter build web --dart-define=API_PORT=...`（一般不推荐与同源混用）。

## 6. Hugging Face / 模型

- 生产首次拉模型可能超时：配置 `HF_ENDPOINT`、`HF_HUB_DOWNLOAD_TIMEOUT`，或镜像内预缓存模型目录并设置 `HF_HOME`
