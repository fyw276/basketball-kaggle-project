# 清除可能影响 Claude 的 Anthropic 官方环境变量（仅当前 shell 会话）
unset ANTHROPIC_AUTH_TOKEN
unset ANTHROPIC_BASE_URL
echo "已从当前 shell 会话移除 ANTHROPIC_AUTH_TOKEN 和 ANTHROPIC_BASE_URL（若存在）。"
