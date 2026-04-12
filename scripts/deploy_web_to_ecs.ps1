param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$RemoteWebRoot = "/usr/share/nginx/html",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

Write-Host "[1/6] Checking required commands..." -ForegroundColor Cyan
Test-CommandAvailable "ssh"
Test-CommandAvailable "scp"
Test-CommandAvailable "tar"

$mobileDir = Join-Path $ProjectRoot "mobile"
$buildWebDir = Join-Path $mobileDir "build/web"

if (-not (Test-Path $mobileDir)) {
    throw "Mobile directory not found: $mobileDir"
}

if (-not $SkipBuild) {
    Write-Host "[2/6] Building Flutter web..." -ForegroundColor Cyan
    Test-CommandAvailable "flutter"
    Push-Location $mobileDir
    try {
        flutter pub get
        if ($LASTEXITCODE -ne 0) { throw "flutter pub get failed" }

        flutter build web --release
        if ($LASTEXITCODE -ne 0) { throw "flutter build web failed" }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[2/6] Skip build enabled." -ForegroundColor Yellow
}

if (-not (Test-Path $buildWebDir)) {
    throw "Build output not found: $buildWebDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$localTar = Join-Path $mobileDir "web-$timestamp.tar.gz"
$remoteTar = "/tmp/web-$timestamp.tar.gz"
$remote = "$User@$ServerHost"

Write-Host "[3/6] Packing build output..." -ForegroundColor Cyan
if (Test-Path $localTar) {
    Remove-Item -Force $localTar
}

tar -C $buildWebDir -czf $localTar .
if ($LASTEXITCODE -ne 0) { throw "tar pack failed" }

Write-Host "[4/6] Uploading package to $remote..." -ForegroundColor Cyan
scp $localTar "$remote`:$remoteTar"
if ($LASTEXITCODE -ne 0) { throw "scp upload failed" }

Write-Host "[5/6] Publishing on server and reloading nginx..." -ForegroundColor Cyan
$remoteScript = @"
set -e
mkdir -p '$RemoteWebRoot'
rm -rf '$RemoteWebRoot'/*
tar -xzf '$remoteTar' -C '$RemoteWebRoot'
nginx -t
systemctl reload nginx
rm -f '$remoteTar'
echo 'Deploy finished'
"@

ssh $remote $remoteScript
if ($LASTEXITCODE -ne 0) { throw "remote deploy failed" }

Write-Host "[6/6] Cleaning local temp package..." -ForegroundColor Cyan
if (Test-Path $localTar) {
    Remove-Item -Force $localTar
}

Write-Host "Done. Please hard refresh browser with Ctrl+F5." -ForegroundColor Green
