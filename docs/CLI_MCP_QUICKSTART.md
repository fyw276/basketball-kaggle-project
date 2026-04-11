# CLI + MCP Quickstart

## 当前状态

- CLI 工具：已提供 MVP
- MCP 服务：已提供 MVP

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

- `health`
- `login`
- `list_wardrobe`
- `analyze_similarity`
- `recommend_outfits`
- `analyze_suitability`

## 说明

- CLI 默认输出 JSON，适合脚本自动化。
- MCP 工具通过后端 API 转发能力，认证基于 `OUTFIT_API_TOKEN`。
- 若你希望我继续，我可以下一步补：
  - MCP 工具 schema 更严格的参数校验
  - CLI 更友好的表格输出模式
  - CI 中加入 CLI/MCP 专项测试

## 测试

```bash
cd backend
python -m pytest tests_lite/test_cli_mcp_mvp_lite.py -v --tb=short
```
