# 智能穿搭（Flutter Web）实现说明与排障

本文记录智能穿搭端到端在 **Flutter Web + 本机 FastAPI** 下的关键实现，便于维护与排障。业务接口前缀均为 **`/api/v1/smart-outfit/*`**（需登录，Bearer Token）。

## 功能概览

- **参考图**：上传 → `POST /smart-outfit/upload-reference` → 得到 `image_url`。
- **天气与地址**：GPS 经纬度 → `GET /smart-outfit/weather`；或手动选城 → `GET /smart-outfit/weather-by-city`。展示字段使用服务端逆地理/天气，**不在 UI 展示裸经纬度**。
- **生成**：`POST /smart-outfit/generate`，JSON 含 `image_url`、`location`、`city`、`weather`、`temperature`、`mood`、`count`、`regeneration_index`、可选 `gender_expression`。
- **结果**：`PageView` 展示多套方案；Web 上支持鼠标横向拖拽翻页；布局随窗口宽度/高度自适应。

## 前端要点（`mobile/lib`）

| 主题 | 说明 |
|------|------|
| **API 基址** | `api_base_resolver_web.dart`：本机 loopback 时 API 的 **host 与浏览器地址栏一致**（`localhost` ↔ `localhost:8000`，`127.0.0.1` ↔ `127.0.0.1:8000`），避免 `localhost` 页面请求 `127.0.0.1` API 触发 Chrome 私有网络预检问题。局域网调试仍用页面同源 IP。 |
| **认证顺序** | `AuthProvider` 异步从 `SharedPreferences` 恢复 token。`SmartOutfitScreen` 在请求天气/生成前 **`_waitForAuthReady()`**，避免无 `Authorization` 的 401 被误报为「无法获取天气」或生成失败。 |
| **衣橱图片 URL** | `core/utils/media_url.dart`：`resolveGarmentImageUrl` 将相对路径与混用 host 的绝对 URL 对齐到当前 API 源站；`/uploads/` 路径大小写不敏感兼容历史数据。 |
| **衣橱缩略图** | `wardrobe_screen.dart`：`Image.network` 在 Web 上使用 `webHtmlElementStrategy: prefer`，与 `PlatformImage` 一致，减轻跨端口加载问题。 |
| **生成请求** | `ApiClient.generateSmartOutfit` 使用 `package:http` 的 `POST`，`baseUrl` 在构造函数中去掉尾部 `/`；超时 180s。 |
| **搭配轮播** | `ScrollConfiguration` + 自定义 `MaterialScrollBehavior`，`dragDevices` 包含 `mouse` / `trackpad`，否则 Web 上无法横向拖动 `PageView`。 |
| **响应式** | 主内容 `LayoutBuilder` + `ConstrainedBox(maxWidth: min(可用宽, 520))`；`PageController(viewportFraction: 1.0)` 避免右侧露出下一张被裁切；搭配区高度随窗口 `clamp`。 |

## 后端要点（`backend/app`）

| 主题 | 说明 |
|------|------|
| **CORS** | `main.py`：`Authorization`、`Content-Type` 等显式列入 `allow_headers`（避免仅 `*` 时预检对 Bearer 不通过）。开发环境对 `localhost` / `127.0.0.1` 任意端口使用 `allow_origin_regex`。 |
| **私有网络 (PNA)** | `PrivateNetworkAccessMiddleware` 为响应附加 `Access-Control-Allow-Private-Network: true`；预检请求头列表含 `Access-Control-Request-Private-Network`。 |
| **静态资源 URL** | `services/storage.py`：`_public_base_url()` → `http://127.0.0.1:{settings.PORT}`，保存文件时入库的 `image_url` 与端口一致，避免硬编码 8000 与 `PORT` 不一致。 |
| **天气** | `weather_service.py`：Open-Meteo + 可选 Nominatim 逆地理；智能穿搭路由见 `api/smart_outfit.py`。 |

## 常见问题

1. **天气失败 + 默认参数**：多为请求早于 token 恢复；确认已登录并热重载后重试。Network 中 `weather` 若 401，即为未带 Token。
2. **生成报「无法连接」**：后端是否监听、防火墙；CORS/PNA 是否生效（重启后端）。`OPTIONS` 与正式 `POST` 的响应头是否正常。
3. **衣橱部分图不加载**：检查 Network 中图片 URL 是否 404；`resolveGarmentImageUrl` 是否将 `127.0.0.1` 与当前 API host 对齐。
4. **Web 无法左右滑搭配卡**：确认已包含鼠标 `dragDevices` 的 `ScrollConfiguration`（见 `smart_outfit_screen.dart`）。

## 相关文件索引

- 页面：`mobile/lib/features/analysis/screens/smart_outfit_screen.dart`
- API：`mobile/lib/core/services/api_client.dart`
- Web API 基址：`mobile/lib/core/services/api_base_resolver_web.dart`
- 图片 URL：`mobile/lib/core/utils/media_url.dart`
- 后端入口与中间件：`backend/app/main.py`
- 存储 URL：`backend/app/services/storage.py`
