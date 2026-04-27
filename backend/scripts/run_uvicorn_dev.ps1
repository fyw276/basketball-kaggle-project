# 本机开发：启动 Smart Outfit 后端（默认端口与 .env / Flutter kApiPort 一致，当前为 8010）。
# 用法（在 backend 目录下）:
#   .\scripts\run_uvicorn_dev.ps1
#   .\scripts\run_uvicorn_dev.ps1 -Port 8000
# 释放端口后再启动（结束占用该端口的监听进程）:
#   .\scripts\run_uvicorn_dev.ps1 -KillExisting
param(
    [int]$Port = 8010,
    [switch]$KillExisting
)

$ErrorActionPreference = "Stop"
$backendRoot = Split-Path -Parent $PSScriptRoot
Set-Location $backendRoot

if ($KillExisting) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        try {
            $p = Get-Process -Id $procId -ErrorAction Stop
            Write-Host "[run_uvicorn_dev] Stopping PID $procId ($($p.ProcessName)) on port $Port"
            Stop-Process -Id $procId -Force
        } catch {
            Write-Warning "Could not stop PID $procId : $_"
        }
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "[run_uvicorn_dev] Starting uvicorn on 0.0.0.0:$Port (cwd: $backendRoot)"
$env:TF_ENABLE_ONEDNN_OPTS = "0"
$env:HF_HOME = "D:\hf-cache"
$env:HF_ENDPOINT = "https://hf-mirror.com"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port $Port
