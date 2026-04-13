param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$RemoteAppRoot = "/opt/clothing-assistant/clothing-assistant-main",
    [string]$RemoteWebRoot = "/usr/share/nginx/html",
    [string]$RemoteEnvFile = "/opt/clothing-assistant/clothing-assistant-main/backend/.env",
    [string]$RemoteHealthUrl = "http://127.0.0.1:8010/health"
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Test-CommandAvailable "ssh"
Test-CommandAvailable "scp"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localAudit = Join-Path $PSScriptRoot "full_chain_consistency_audit.sh"
if (-not (Test-Path $localAudit)) {
    throw "Local script not found: $localAudit"
}

$remote = "$User@$ServerHost"
$remoteAudit = "/tmp/full_chain_consistency_audit.sh"

Write-Host "[1/3] Uploading audit script to $remote..." -ForegroundColor Cyan
scp $localAudit "$remote`:$remoteAudit"
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed"
}

Write-Host "[2/3] Executing audit on remote host..." -ForegroundColor Cyan
# Use one-line command and strip CR to avoid $'\r' path issues on Linux shells.
$remoteCmd = "chmod +x '$remoteAudit'; APP_ROOT='$RemoteAppRoot' WEB_ROOT='$RemoteWebRoot' ENV_FILE='$RemoteEnvFile' HEALTH_URL='$RemoteHealthUrl' bash '$remoteAudit'"
$remoteCmd = $remoteCmd -replace "`r", ""

ssh $remote $remoteCmd
$code = $LASTEXITCODE

Write-Host "[3/3] Cleaning remote temp file..." -ForegroundColor Cyan
ssh $remote "rm -f '$remoteAudit'" | Out-Null

if ($code -eq 2) {
    throw "Remote audit failed with exit code: $code"
}
if ($code -eq 1) {
    Write-Host "Remote audit completed with warnings (exit=1)." -ForegroundColor Yellow
    exit 0
}

Write-Host "Remote audit completed successfully." -ForegroundColor Green
