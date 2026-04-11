param(
    [string]$BackendHost = "127.0.0.1",
    [int]$BackendPort = 8010,
    [string]$ApiToken = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python not found at $pythonExe"
    exit 1
}

$apiBase = "http://$BackendHost`:$BackendPort/api/v1"

$backendCmd = "Set-Location '$repoRoot\backend'; & '$pythonExe' -m uvicorn app.main:app --host $BackendHost --port $BackendPort"
$mcpCmd = "$env:OUTFIT_API_BASE_URL='$apiBase'; "
if ($ApiToken -ne "") {
    $mcpCmd += "$env:OUTFIT_API_TOKEN='$ApiToken'; "
}
$mcpCmd += "Set-Location '$repoRoot'; & '$pythonExe' mcp/server.py"

Write-Host "Starting backend: $BackendHost:$BackendPort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd | Out-Null

Write-Host "Starting MCP server with API base: $apiBase"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $mcpCmd | Out-Null

Write-Host "Done. Two terminals were opened (backend and mcp)."
if ($ApiToken -eq "") {
    Write-Host "Note: ApiToken is empty. MCP tools requiring auth will fail until OUTFIT_API_TOKEN is set."
}
