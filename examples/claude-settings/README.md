示例：Claude / MiMo 配置文件

目录包含用于快速生成并复制到用户主目录的示例配置文件：

- `settings.json.example`：示例 `~/.claude/settings.json` 内容
- `claude.json.example`：示例 `~/.claude.json` 内容
- `clear_env.ps1`：在 Windows PowerShell 中移除可能干扰的环境变量（仅当前会话）
- `clear_env.sh`：在 macOS/Linux bash 中移除可能干扰的环境变量（仅当前会话）
 - `enable_1m_context.ps1`：Windows PowerShell 脚本，修改 `~/.claude/settings.json` 为带 `[1m]` 的模型 ID 并尝试打开新 PowerShell 窗口
 - `enable_1m_context.sh`：macOS/Linux 脚本，修改 `~/.claude/settings.json` 为带 `[1m]` 的模型 ID 并尝试打开新终端窗口

使用方法：
1. 将 `settings.json.example` 复制到 `%USERPROFILE%\.claude\settings.json`，并把 `YOUR_MIMO_API_KEY` 替换成你的真实密钥。
2. 复制 `claude.json.example` 到用户目录下 `~/.claude.json`。
3. 关闭并重开终端，进入项目目录运行 `claude`，使用 `/status` 与 `/context` 校验配置。

Windows 最终版位置：
- 主配置文件放到 `%USERPROFILE%\.claude\settings.json`
- 这个仓库里的示例文件只用于复制，不会被 Claude Code 自动读取
- 如果你的服务端要求 1M 上下文，模型名必须保留 `[1m]` 后缀，例如 `mimo-v2.5-pro[1m]`

启用 1M 长上下文：
- 在已创建的 `~/.claude/settings.json` 基础上，运行下面脚本将模型 ID 更新为带 `[1m]` 后缀并尝试打开新终端（Windows/Linux/macOS）：
	- PowerShell（在 Windows 本机运行）：
		- [examples/claude-settings/enable_1m_context.ps1](examples/claude-settings/enable_1m_context.ps1)
	- macOS / Linux（在本机运行）：
		- [examples/claude-settings/enable_1m_context.sh](examples/claude-settings/enable_1m_context.sh)

运行脚本后，请关闭旧终端或在新打开的终端中运行 `claude /context` 验证长上下文是否生效。

注意：不要在公开聊天中贴入真实密钥；在本地编辑时再替换占位符。
