param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$RemoteWebRoot = "/usr/share/nginx/html",
    [string]$RemoteAppRoot = "/opt/clothing-assistant/clothing-assistant-main",
    [string]$BackendService = "clothing-backend",
    [string]$BackendHealthUrl = "http://127.0.0.1:8010/health",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [switch]$SkipWebBuild,
    [switch]$SkipWebDeploy,
    [switch]$SkipBackendDeploy,
    [switch]$SkipBackendRestart
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Invoke-RemoteBash {
    param(
        [string]$Remote,
        [string]$ScriptText
    )

    # Normalize to LF to avoid CRLF breaking remote bash parsing.
    $normalized = ($ScriptText -replace "`r", "").TrimEnd("`n") + "`n"
    $tmp = [System.IO.Path]::GetTempFileName()
    $remoteTmp = "/tmp/copilot-deploy-$([guid]::NewGuid().ToString('N')).sh"
    $oldErrorAction = $ErrorActionPreference
    try {
        # Native commands may write warnings to stderr (e.g. nginx -t warning)
        # while still succeeding; do not fail early on stderr text.
        $ErrorActionPreference = "Continue"

        [System.IO.File]::WriteAllText($tmp, $normalized, [System.Text.UTF8Encoding]::new($false))
        $scpOut = scp $tmp "$Remote`:$remoteTmp" 2>&1
        $scpCode = $LASTEXITCODE
        if ($scpCode -ne 0) {
            $msg = (($scpOut | ForEach-Object { $_.ToString() }) -join "`n").Trim()
            if (-not $msg) { $msg = "(no scp output)" }
            throw "remote script upload failed (exit=$scpCode)`n$msg"
        }

        $sshOut = ssh $Remote "bash '$remoteTmp'" 2>&1
        $sshCode = $LASTEXITCODE
        if ($sshOut) {
            ($sshOut | ForEach-Object { $_.ToString() }) | ForEach-Object { Write-Host $_ }
        }
        if ($sshCode -ne 0) {
            $msg = (($sshOut | ForEach-Object { $_.ToString() }) -join "`n").Trim()
            if (-not $msg) { $msg = "(no remote output)" }
            throw "remote bash failed (exit=$sshCode)`n$msg"
        }
    }
    finally {
        $ErrorActionPreference = "Continue"
        ssh $Remote "rm -f '$remoteTmp'" 2>$null | Out-Null
        $ErrorActionPreference = $oldErrorAction
        if (Test-Path $tmp) {
            Remove-Item -Force $tmp
        }
    }
}

Write-Host "[1/9] Checking required commands..." -ForegroundColor Cyan
Test-CommandAvailable "ssh"
Test-CommandAvailable "scp"
Test-CommandAvailable "tar"

$mobileDir = Join-Path $ProjectRoot "mobile"
$buildWebDir = Join-Path $mobileDir "build/web"
$backendDir = Join-Path $ProjectRoot "backend"

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}

if (-not $SkipWebDeploy -and -not $SkipWebBuild) {
    Write-Host "[2/9] Building Flutter web..." -ForegroundColor Cyan
    if (-not (Test-Path $mobileDir)) {
        throw "Mobile directory not found: $mobileDir"
    }
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
    Write-Host "[2/9] Skip web build." -ForegroundColor Yellow
}

if (-not $SkipWebDeploy -and -not (Test-Path $buildWebDir)) {
    throw "Build output not found: $buildWebDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$localWebTar = Join-Path $mobileDir "web-$timestamp.tar.gz"
$localBackendTar = Join-Path $ProjectRoot "backend-$timestamp.tar.gz"
$remoteWebTar = "/tmp/web-$timestamp.tar.gz"
$remoteBackendTar = "/tmp/backend-$timestamp.tar.gz"
$remote = "$User@$ServerHost"

try {
    if (-not $SkipWebDeploy) {
        Write-Host "[3/9] Packing web build..." -ForegroundColor Cyan
        if (Test-Path $localWebTar) {
            Remove-Item -Force $localWebTar
        }
        tar -C $buildWebDir -czf $localWebTar .
        if ($LASTEXITCODE -ne 0) { throw "tar web pack failed" }
    }
    else {
        Write-Host "[3/9] Skip web package/deploy." -ForegroundColor Yellow
    }

    if (-not $SkipBackendDeploy) {
        Write-Host "[4/9] Packing backend source..." -ForegroundColor Cyan
        if (Test-Path $localBackendTar) {
            Remove-Item -Force $localBackendTar
        }
        tar -C $ProjectRoot -czf $localBackendTar `
            --exclude "backend/.pytest_cache" `
            --exclude "backend/__pycache__" `
            --exclude "backend/uploads" `
            --exclude "backend/logs" `
            --exclude "backend/.env" `
            --exclude "backend/.env.*" `
            --exclude "backend/*.db" `
            --exclude "backend/*.sqlite" `
            --exclude "backend/*.sqlite3" `
            --exclude "backend/.mypy_cache" `
            backend
        if ($LASTEXITCODE -ne 0) { throw "tar backend pack failed" }
    }
    else {
        Write-Host "[4/9] Skip backend package/deploy." -ForegroundColor Yellow
    }

    Write-Host "[5/9] Uploading packages to $remote..." -ForegroundColor Cyan
    if (-not $SkipWebDeploy) {
        scp $localWebTar "$remote`:$remoteWebTar"
        if ($LASTEXITCODE -ne 0) { throw "scp web upload failed" }
    }
    if (-not $SkipBackendDeploy) {
        scp $localBackendTar "$remote`:$remoteBackendTar"
        if ($LASTEXITCODE -ne 0) { throw "scp backend upload failed" }
    }

    Write-Host "[6/9] Publishing on server..." -ForegroundColor Cyan
    $doWeb = if ($SkipWebDeploy) { "0" } else { "1" }
    $doBackend = if ($SkipBackendDeploy) { "0" } else { "1" }
    $doRestart = if ($SkipBackendRestart) { "0" } else { "1" }

        $remoteScriptTemplate = @'
    set -Eeuo pipefail
    trap 'echo "[remote][ERROR] line=$LINENO cmd=$BASH_COMMAND" >&2' ERR

    DO_WEB='__DO_WEB__'
    DO_BACKEND='__DO_BACKEND__'
    DO_RESTART='__DO_RESTART__'
    REMOTE_WEB_ROOT='__REMOTE_WEB_ROOT__'
    REMOTE_APP_ROOT='__REMOTE_APP_ROOT__'
    REMOTE_WEB_TAR='__REMOTE_WEB_TAR__'
    REMOTE_BACKEND_TAR='__REMOTE_BACKEND_TAR__'
    BACKEND_SERVICE='__BACKEND_SERVICE__'
    BACKEND_HEALTH_URL='__BACKEND_HEALTH_URL__'
    resolved_unit=""

if [ "$DO_WEB" = "1" ]; then
    echo "[remote] Deploying web to $REMOTE_WEB_ROOT"
    mkdir -p "$REMOTE_WEB_ROOT"
    rm -rf "$REMOTE_WEB_ROOT"/*
    tar -xzf "$REMOTE_WEB_TAR" -C "$REMOTE_WEB_ROOT"
    nginx -t
    systemctl reload nginx
fi

if [ "$DO_BACKEND" = "1" ]; then
    echo "[remote] Deploying backend to $REMOTE_APP_ROOT"
    mkdir -p "$REMOTE_APP_ROOT"
    tar -xzf "$REMOTE_BACKEND_TAR" -C "$REMOTE_APP_ROOT"
fi

if [ "$DO_RESTART" = "1" ]; then
    echo "[remote] Restarting service $BACKEND_SERVICE"
    unit_list="$(systemctl list-unit-files --type=service --no-legend | awk '{print $1}')"
    desired="$BACKEND_SERVICE"
    with_suffix="$BACKEND_SERVICE"
    if [[ "$with_suffix" != *.service ]]; then
        with_suffix="$with_suffix.service"
    fi

    resolved_unit=""
    if printf '%s\n' "$unit_list" | grep -Fxq "$desired"; then
        resolved_unit="$desired"
    elif printf '%s\n' "$unit_list" | grep -Fxq "$with_suffix"; then
        resolved_unit="$with_suffix"
    fi

    if [ -z "$resolved_unit" ]; then
        echo "[remote][ERROR] service not found: $BACKEND_SERVICE" >&2
        systemctl list-unit-files --type=service --no-legend | grep -E "clothing|backend" || true
        exit 21
    fi

    echo "[remote] Resolved unit: $resolved_unit"
    systemctl restart "$resolved_unit"
    systemctl --no-pager --full status "$resolved_unit" | sed -n '1,20p'
fi

echo "[remote] Health check: $BACKEND_HEALTH_URL"
health_ok=0
for i in $(seq 1 45); do
    if command -v curl >/dev/null 2>&1; then
        if curl -fsS "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
            health_ok=1
            break
        fi
    else
        if wget -q -O /dev/null "$BACKEND_HEALTH_URL" >/dev/null 2>&1; then
            health_ok=1
            break
        fi
    fi
    sleep 1
done

if [ "$health_ok" != "1" ]; then
    echo "[remote][ERROR] health check failed after retry: $BACKEND_HEALTH_URL" >&2
    diag_unit="$BACKEND_SERVICE"
    if [ -n "$resolved_unit" ]; then
        diag_unit="$resolved_unit"
    fi
    systemctl --no-pager --full status "$diag_unit" | sed -n '1,60p' || true
    journalctl -u "$diag_unit" -n 80 --no-pager || true
    ss -lntp | grep 8010 || true
    exit 7
fi
echo "[remote] Health check passed"

rm -f "$REMOTE_WEB_TAR" "$REMOTE_BACKEND_TAR"
echo "Deploy finished"
'@

    $remoteScript = $remoteScriptTemplate
    $remoteScript = $remoteScript.Replace('__DO_WEB__', $doWeb)
    $remoteScript = $remoteScript.Replace('__DO_BACKEND__', $doBackend)
    $remoteScript = $remoteScript.Replace('__DO_RESTART__', $doRestart)
    $remoteScript = $remoteScript.Replace('__REMOTE_WEB_ROOT__', $RemoteWebRoot)
    $remoteScript = $remoteScript.Replace('__REMOTE_APP_ROOT__', $RemoteAppRoot)
    $remoteScript = $remoteScript.Replace('__REMOTE_WEB_TAR__', $remoteWebTar)
    $remoteScript = $remoteScript.Replace('__REMOTE_BACKEND_TAR__', $remoteBackendTar)
    $remoteScript = $remoteScript.Replace('__BACKEND_SERVICE__', $BackendService)
    $remoteScript = $remoteScript.Replace('__BACKEND_HEALTH_URL__', $BackendHealthUrl)

    Invoke-RemoteBash -Remote $remote -ScriptText $remoteScript

    Write-Host "[7/9] Verifying smart-outfit hotfix markers on server..." -ForegroundColor Cyan
    $verifyScript = @"
set -e
grep -n "application/octet-stream" "$RemoteAppRoot/backend/app/api/smart_outfit.py" >/dev/null
grep -n "No outfit cards generated from wardrobe" "$RemoteAppRoot/backend/app/services/smart_outfit_generator.py" >/dev/null
echo "Backend hotfix markers found"
"@
    Invoke-RemoteBash -Remote $remote -ScriptText $verifyScript
}
finally {
    Write-Host "[8/9] Cleaning local temporary packages..." -ForegroundColor Cyan
    if (Test-Path $localWebTar) {
        Remove-Item -Force $localWebTar
    }
    if (Test-Path $localBackendTar) {
        Remove-Item -Force $localBackendTar
    }
}

Write-Host "[9/9] Done. Please hard refresh browser with Ctrl+F5." -ForegroundColor Green
