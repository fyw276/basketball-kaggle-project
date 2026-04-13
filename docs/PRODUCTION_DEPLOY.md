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

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

验收：

```bash
curl -fsS https://your-domain/health
curl -fsS https://your-domain/health/ready
```

## 3. 持久化（P0）

- **`UPLOAD_DIR`**（默认 `./uploads`）：挂载 **云盘或 NAS**，避免实例重建后图片全部丢失
- 数据库使用托管或独立磁盘，**勿**依赖容器可写层长期存数据

## 4. 就绪与限流（P1）

- **就绪探针**：`GET /health/ready`（检查数据库）；负载均衡/编排将流量打到就绪实例
- **存活探针**：`GET /health`
- **限流**：`.env` 中 `ENABLE_RATE_LIMIT=true` 且 `RATE_LIMIT_PER_MINUTE=60`（或按需）；多 worker 进程下为**每进程**计数，需网关层限流时请同时在 SLB/WAF 配置

## 5. 与脚本 `deploy_full_to_ecs.ps1` 的配合

- 脚本**不包含** `.env`：首次在服务器创建 `backend/.env` 并按上表填写
- Flutter Web 线上默认使用 **当前页 `origin` + `/api/v1`**，依赖上述 Nginx；若需异常架构再使用 `flutter build web --dart-define=API_PORT=...`（一般不推荐与同源混用）

## 6. Hugging Face / 模型

- 生产首次拉模型可能超时：配置 `HF_ENDPOINT`、`HF_HUB_DOWNLOAD_TIMEOUT`，或镜像内预缓存模型目录并设置 `HF_HOME`
