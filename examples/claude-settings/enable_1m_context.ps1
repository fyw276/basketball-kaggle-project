# 将 `~/.claude/settings.json` 中模型字段统一添加 `[1m]` 后缀并尝试打开新 PowerShell 窗口
$claudeDir = Join-Path $HOME ".claude"
$settingsFile = Join-Path $claudeDir "settings.json"
if (-not (Test-Path $settingsFile)) {
    Write-Error "找不到 $settingsFile，请先创建该文件或运行 examples/claude-settings/settings.json.example 的内容。"
    exit 1
}
$content = Get-Content $settingsFile -Raw
try {
    $json = $content | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Error "解析 JSON 失败：$($_.Exception.Message)"
    exit 1
}
function AddSuffix($s) {
    if (-not $s) { return "mimo-v2.5-pro[1m]" }
    if ($s -match "\[1m\]$") { return $s }
    return "$s[1m]"
}
if (-not $json.env) { $json | Add-Member -MemberType NoteProperty -Name env -Value @{} }
$json.env.ANTHROPIC_MODEL = AddSuffix $json.env.ANTHROPIC_MODEL
$json.env.ANTHROPIC_DEFAULT_SONNET_MODEL = AddSuffix $json.env.ANTHROPIC_DEFAULT_SONNET_MODEL
$json.env.ANTHROPIC_DEFAULT_OPUS_MODEL = AddSuffix $json.env.ANTHROPIC_DEFAULT_OPUS_MODEL
$json.env.ANTHROPIC_DEFAULT_HAIKU_MODEL = AddSuffix $json.env.ANTHROPIC_DEFAULT_HAIKU_MODEL

$json | ConvertTo-Json -Depth 10 | Out-File -FilePath $settingsFile -Encoding utf8
Write-Output "已更新：$settingsFile（模型字段已添加 [1m] 后缀，如有缺省则设置为 mimo-v2.5-pro[1m]）。"

# 尝试打开新的 PowerShell 窗口让配置生效（如果失败则提示手动重启）
try {
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","Write-Host '新 PowerShell 窗口已打开；关闭旧窗口以完成配置生效。'"
    Write-Output "已尝试打开新 PowerShell 窗口。"
} catch {
    Write-Warning "无法自动打开新终端，请手动关闭并重新打开终端以使配置生效。"
}
