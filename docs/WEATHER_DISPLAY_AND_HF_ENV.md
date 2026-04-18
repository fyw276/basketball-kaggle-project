# 智能穿搭天气展示与 Hugging Face 环境变量

**最后更新**: 2026-04-04

本文记录与「定位与天气」展示、以及 CLIP / 虚拟试衣模型下载相关的后端行为与配置，便于部署与排障。

## 1. 天气地址展示：过滤道路/线路名

### 背景

逆地理编码（Open-Meteo / Nominatim 等）返回的 `street` 有时是国道、省道或「某某线」等道路名。若直接拼进展示地址，会出现「河北省 沧州市 盐山县 **山深线**」这类对用户不友好的结果；经纬度与天气 API 仍按原坐标请求，仅**展示文案**优化。

### 实现（后端）

- 文件：`backend/app/services/weather_service.py`
- 逻辑：
  - `_is_route_like_road(street)`：识别国道/省道/县道、高速、G 编号路、短「某某线」等线路型道路名。
  - `_display_address_after_route_filter(...)`：当省市区非空且 `street` 被判为线路型时，展示地址**去掉**该 `street`；若仅有线路名而无行政区，则保留 `street`，避免空白。
- 接入点：`fetch_weather_lat_lon`、`fetch_weather_by_city_name` 在组装展示用 `full_line` 后、请求天气 API 前调用上述过滤。

### 测试

- `backend/tests/test_weather_service_display.py`：覆盖 `_is_route_like_road` 与 `_display_address_after_route_filter` 的典型用例。

---

## 2. Hugging Face：`.env` 与进程环境变量同步

### 背景

`huggingface_hub` / `diffusers` 只读取 **`os.environ`**。若仅在 `.env` 中写入 `HF_ENDPOINT` 等变量，但未注入进程环境，国内镜像**不会生效**，易导致 CLIP 或虚拟试衣首次下载超时、SSL 断连。

### 实现（后端）

- `backend/app/core/config.py`：`Settings` 中声明 `HF_ENDPOINT`、`HF_HOME`、`HF_TOKEN`、`TRANSFORMERS_CACHE`、`HF_HUB_DOWNLOAD_TIMEOUT`（空字符串表示未设置）。
- `backend/app/core/hf_hub_env.py`：`sync_hf_env_from_settings(settings)` 将非空配置项写入 `os.environ`；`apply_hf_hub_env_defaults()` 为未设置的键提供合理默认（如下载超时等）。
- `backend/app/main.py`：在首次加载任何 HF 模型之前依次调用 `sync_hf_env_from_settings(settings)` 与 `apply_hf_hub_env_defaults()`。

### 推荐配置（国内）

在 `backend/.env` 中例如：

```env
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DOWNLOAD_TIMEOUT=600
```

虚拟试衣需下载多 GB 权重，超时建议不低于 300～600 秒。修改后需**重启**后端进程。

### 预下载与离线

- 脚本：`backend/scripts/prefetch_models.py`（`--clip`、`--tryon` 等）。
- 离线部署可将缓存目录拷至目标机，并配合 `HF_HOME` / `HF_HUB_OFFLINE` 等（见 `backend/.env.example`）。

### 虚拟试衣不可用时的常见原因

首次生成会从 Hugging Face 拉取 `stable-diffusion-v1-5/stable-diffusion-inpainting`（或 `SD_VTON_MODEL_ID` 指定模型）。若日志出现 `cas-bridge.xethub.hf.co`、`Read timed out`、`SSLError`，属于**网络或缓存不完整**，按上文配置镜像、清理半截缓存后重试，或换稳定网络/代理。

---

## 相关文件一览

| 区域 | 路径 |
|------|------|
| 天气展示过滤 | `backend/app/services/weather_service.py` |
| HF 环境同步 | `backend/app/core/config.py`, `backend/app/core/hf_hub_env.py`, `backend/app/main.py` |
| 示例环境变量 | `backend/.env.example` |
| 天气展示测试 | `backend/tests/test_weather_service_display.py` |
