# Start standalone outfit predict API (backend.main).
# Default port 8765 — high range avoids many WinError 10048/10013 issues with 8000–8010 on Windows.
#
# Usage (from repo root):
#   .\scripts\run_predict_api.ps1
#   .\scripts\run_predict_api.ps1 -Port 9888
#   .\scripts\run_predict_api.ps1 -NoReload    # if WinError 10013 persists (socket access denied)
#
# Check excluded port ranges (Hyper-V / Docker can reserve ranges):
#   netsh interface ipv4 show excludedportrange protocol=tcp

param(
    [int] $Port = 8765,
    [switch] $NoReload
)

Set-Location (Split-Path $PSScriptRoot -Parent)

$reloadArgs = @()
if (-not $NoReload) {
    $reloadArgs = @('--reload')
}

Write-Host "Starting backend.main on http://127.0.0.1:$Port/docs (predict: /predict)" -ForegroundColor Cyan

& python -m uvicorn backend.main:app @reloadArgs --host 127.0.0.1 --port $Port
