#!/usr/bin/env bash
# 将 `~/.claude/settings.json` 中模型字段统一添加 `[1m]` 后缀，并尝试开启新终端窗口（若不可用则提示手动重启）
set -euo pipefail
CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"
if [ ! -f "$SETTINGS" ]; then
  echo "找不到 $SETTINGS，请先创建该文件或使用 examples/claude-settings/settings.json.example 的内容。"
  exit 1
fi

python3 - <<PY
import json,os,sys
f = os.path.expanduser('$SETTINGS')
try:
    j = json.load(open(f, 'r', encoding='utf8'))
except Exception as e:
    print('解析 JSON 失败:', e)
    sys.exit(1)
def addsuffix(s):
    if not s:
        return 'mimo-v2.5-pro[1m]'
    if s.endswith('[1m]'):
        return s
    return s + '[1m]'
env = j.get('env', {})
env['ANTHROPIC_MODEL'] = addsuffix(env.get('ANTHROPIC_MODEL'))
env['ANTHROPIC_DEFAULT_SONNET_MODEL'] = addsuffix(env.get('ANTHROPIC_DEFAULT_SONNET_MODEL'))
env['ANTHROPIC_DEFAULT_OPUS_MODEL'] = addsuffix(env.get('ANTHROPIC_DEFAULT_OPUS_MODEL'))
env['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = addsuffix(env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL'))
j['env'] = env
with open(f, 'w', encoding='utf8') as fh:
    json.dump(j, fh, indent=2, ensure_ascii=False)
print('已更新:', f)
PY

echo "尝试打开新交互式 shell（如果系统支持）。若未能打开，请手动关闭并重新打开你的终端窗口以使配置生效。"
# Linux: 尝试使用常见终端打开新窗口（不保证存在）
if command -v gnome-terminal >/dev/null 2>&1; then
  gnome-terminal -- bash -lc "exec bash"
elif command -v konsole >/dev/null 2>&1; then
  konsole --noclose -e bash -i &
elif [[ "$OSTYPE" == "darwin"* ]] && command -v osascript >/dev/null 2>&1; then
  osascript -e 'tell application "Terminal" to do script "exec $SHELL -l"'
else
  echo "未检测到可自动打开的新终端命令；请手动重启你的终端。"
fi
