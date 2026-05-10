示例：Claude / MiMo 配置文件

目录包含用于快速生成并复制到用户主目录的示例配置文件：

- `settings.json.example`：示例 `~/.claude/settings.json` 内容
- `claude.json.example`：示例 `~/.claude.json` 内容
- `clear_env.ps1`：在 Windows PowerShell 中移除可能干扰的环境变量（仅当前会话）
- `clear_env.sh`：在 macOS/Linux bash 中移除可能干扰的环境变量（仅当前会话）

使用方法：
1. 复制 `settings.json.example` 到你的用户目录下的 `.claude/settings.json`，并替换 `BASE_URL` 与 `MIMO_API_KEY` 占位符。
2. 复制 `claude.json.example` 到用户目录下 `~/.claude.json`。
3. 关闭并重开终端，进入项目目录运行 `claude`，使用 `/status` 与 `/context` 校验配置。

注意：不要在公开聊天中贴入真实密钥；在本地编辑时再替换占位符。
