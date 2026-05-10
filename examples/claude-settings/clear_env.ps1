# 清除可能影响 Claude 的 Anthropic 官方环境变量（仅当前 PowerShell 会话）
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_BASE_URL -ErrorAction SilentlyContinue
Write-Output "已从当前 PowerShell 会话移除 ANTHROPIC_AUTH_TOKEN 和 ANTHROPIC_BASE_URL（若存在）。"
