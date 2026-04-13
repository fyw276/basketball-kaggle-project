# CLI + MCP Quickstart

## 当前状态

- CLI：已覆盖认证、衣橱、分析、智能穿搭、情绪、虚拟试衣、套装收藏；输出 JSON，并与后端 **Envelope** 对齐（成功结果为内层 `data`）
- MCP：FastMCP 桥接同一套后端 API，工具列表见下文

## 文件位置

- CLI: `cli/outfit_cli.py`
- MCP: `mcp/server.py`

## CLI 使用

### 1. 查看帮助

```bash
python cli/outfit_cli.py --help
```

### 2. 配置 API 地址

```bash
python cli/outfit_cli.py config --base-url http://127.0.0.1:8010/api/v1
```

### 3. 注册与登录（登录支持用户名/邮箱/手机号）

```bash
python cli/outfit_cli.py register --username demo_user --email demo@example.com --password Demo123!@# --phone-number 13800000000
python cli/outfit_cli.py login --identifier demo_user --password Demo123!@#
```

### 4. 查看衣橱

```bash
python cli/outfit_cli.py wardrobe-list
```

### 5. 相似度分析

```bash
python cli/outfit_cli.py similarity --image uploads/demo.jpg
```

### 6. 穿搭推荐（支持多图）

```bash
python cli/outfit_cli.py outfits --images uploads/a.jpg uploads/b.jpg --num-outfits 3 --scene 日常休闲
```

### 7. 适合度评分

```bash
python cli/outfit_cli.py suitability --image uploads/demo.jpg
```

### 8. 按城市查天气（需已登录）

```bash
python cli/outfit_cli.py weather --city 上海
```

### 9. 智能穿搭：上传参考图 → 拿到 `image_url` → 生成

```bash
python cli/outfit_cli.py smart-upload --image uploads/ref.jpg
python cli/outfit_cli.py smart-generate --image-url "/uploads/..." --city 上海 --weather 晴 --temperature 22 --mood "想暖一点" --count 3
```

（`--image-url` 为上一步返回的相对或绝对路径，与后端约定一致。）

### 10. 情绪：列表（无需登录）与推荐（需登录）

```bash
python cli/outfit_cli.py mood-list
python cli/outfit_cli.py mood-recommend --mood sad --include-wardrobe
```

### 11. 虚拟试衣（需登录，耗时较长）

```bash
python cli/outfit_cli.py tryon --garment uploads/garment.jpg --person uploads/person.jpg --model-gender neutral
```

### 12. 套装收藏列表

```bash
python cli/outfit_cli.py collections-list --page 1
```

## MCP 使用

### 0. 一键启动 backend + mcp（推荐）

```bash
# PowerShell
./scripts/run_backend_and_mcp.ps1 -BackendHost 127.0.0.1 -BackendPort 8010 -ApiToken "<your_bearer_token>"
```

脚本会打开两个终端窗口：一个运行 backend，一个运行 mcp。

### 1. 安装依赖

```bash
pip install mcp httpx
```

### 2. 设置环境变量

```bash
# PowerShell
$env:OUTFIT_API_BASE_URL="http://127.0.0.1:8010/api/v1"
$env:OUTFIT_API_TOKEN="<your_bearer_token>"
```

### 3. 启动 MCP 服务

```bash
python mcp/server.py
```

## MCP 提供的工具

与后端能力一致（成功返回均为解包后的业务体，便于 Agent 使用）：

- `health` — 后端健康检查
- `login` — 用户名/邮箱/手机号 + 密码登录
- `list_wardrobe` — 分页衣橱列表
- `analyze_similarity` — 相似度 / 重复购买预警
- `recommend_outfits` — 场景搭配（多图）
- `analyze_suitability` — 适合度与三维度原因
- `get_weather_by_city` — 按城市名查天气上下文
- `upload_smart_outfit_reference` — 智能穿搭参考图上传
- `generate_smart_outfit` — 智能穿搭生成（需先上传得 `image_url`）
- `list_mood_types` — 情绪类型列表（公开接口）
- `recommend_by_mood` — 情绪推荐（可选衣橱匹配）
- `virtual_try_on` — 虚拟试衣（衣物图 + 人物图）
- `list_outfit_collections` — 用户套装收藏列表
- `submit_feedback` — 点赞/踩/采纳/曝光
- `get_analytics_summary` — 飞轮指标（`scope=user|global`）
- `route_agent_intent` — 自然语言 → 建议工具名（无需 token）
- `add_memory_snippet` / `search_memory_snippets` — 轻量记忆 RAG

**CLI** 对应：`feedback-create`、`analytics-summary`、`agent-intent`、`memory-add`、`memory-search`（见上文命令示例可扩写）。

## 说明

- CLI 默认输出 JSON，适合脚本与 **Cursor 等 Agent** 子进程调用。
- MCP 工具通过后端 API 转发；需登录的接口使用 `OUTFIT_API_TOKEN`（Bearer）。
- **动态工具编排**由 MCP Host 在运行时完成，本仓库提供稳定 **工具面** 与 HTTP 契约。
- 可选增强见 [COMPETITION_EXTENSIONS.md](COMPETITION_EXTENSIONS.md)。

## 测试

```bash
cd backend
python -m pytest tests_lite/test_cli_mcp_mvp_lite.py -v --tb=short
```
