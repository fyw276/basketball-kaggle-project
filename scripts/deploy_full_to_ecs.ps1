#requires -Version 5.1
param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$IdentityFile = "",
    [ValidateSet("Tar", "Git")]
    [string]$DeployMode = "Tar",
    [string]$GitBranch = "main",
    [string]$GitRef = "",
    [string]$RemoteWebRoot = "/usr/share/nginx/html",
    [string]$RemoteAppRoot = "/opt/clothing-assistant/clothing-assistant-main",
    [string]$BackendService = "clothing-backend",
    [string]$BackendHealthUrl = "http://127.0.0.1:8010/health",
    [string]$ProjectRoot = "",
    [switch]$SkipWebBuild,
    [switch]$SkipWebDeploy,
    [switch]$SkipBackendDeploy,
    [switch]$SkipBackendRestart,
    [switch]$SkipPostDeployVerify,
    [switch]$VerifyLegacyHotfixMarkers
)

# Deploy: Flutter Web (tar) + backend tar OR remote git pull. SSH BatchMode=yes -> use key (-IdentityFile).
# ServerHost: IP or hostname only (no http:// or trailing /). See deploy/ecs/README.md

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
}

$ServerHost = $ServerHost.Trim()
$ServerHost = $ServerHost -replace "^https?://", "" -replace "/.*$", ""
if (-not $ServerHost) {
    throw "ServerHost is empty after normalization; pass only IP or hostname (e.g. 101.200.127.179)."
}

. (Join-Path $PSScriptRoot "DeployCommon.ps1")

if ($IdentityFile -and -not (Test-Path -LiteralPath $IdentityFile)) {
    throw "IdentityFile not found: $IdentityFile"
}
if (-not $IdentityFile) {
    Write-Host "[deploy] WARNING: -IdentityFile not set. scp/ssh use default keys only; BatchMode=yes will NOT prompt for password." -ForegroundColor Yellow
}

$SshOpts = Get-DeploySshOpts -IdentityFile $IdentityFile
$remote = "$User@$ServerHost"

function Write-SshAuthDeniedHint {
    param(
        [string]$Step,
        [string]$RemoteTarget,
        [string]$KeyPath
    )
    Write-Host ""
    Write-Host "=== SSH authentication failed: $Step ===" -ForegroundColor Red
    Write-Host "Server returned: Permission denied (publickey,...). scp/ssh use BatchMode=yes (no password prompt)."
    Write-Host ""
    Write-Host "What to do:"
    Write-Host "  1) Verify key login (must print 'ok'):"
    $ik = if ($KeyPath) { "`"$KeyPath`"" } else { "`"$env:USERPROFILE\.ssh\id_ed25519`"" }
    Write-Host "       ssh -i $ik ${RemoteTarget} `"echo ok`""
    Write-Host "  2) If step 1 fails: install your PUBLIC key on the server:"
    Write-Host "       type `$env:USERPROFILE\.ssh\id_ed25519.pub | ssh root@<IP> `"mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`""
    Write-Host "  3) Re-run deploy with: -IdentityFile `"$env:USERPROFILE\.ssh\id_ed25519`""
    Write-Host "  See also: deploy/ecs/README.md (SSH section)"
    Write-Host ""
}

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

    $normalized = ($ScriptText -replace "`r", "").TrimEnd("`n") + "`n"
    $tmp = [System.IO.Path]::GetTempFileName()
    $remoteTmp = "/tmp/copilot-deploy-$([guid]::NewGuid().ToString('N')).sh"
    $oldErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"

        [System.IO.File]::WriteAllText($tmp, $normalized, [System.Text.UTF8Encoding]::new($false))
        $scpCode = Invoke-DeployScp -SshOpts $SshOpts -Source $tmp -Destination "${Remote}:$remoteTmp"
        if ($scpCode -ne 0) {
            Write-SshAuthDeniedHint -Step "remote script upload (scp)" -RemoteTarget $Remote -KeyPath $IdentityFile
            throw "remote script upload failed (exit=$scpCode)"
        }

        $sshOut = & ssh @SshOpts $Remote "bash '$remoteTmp'" 2>&1
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
        & ssh @SshOpts $Remote "rm -f '$remoteTmp'" 2>$null | Out-Null
        $ErrorActionPreference = $oldErrorAction
        if (Test-Path $tmp) {
            Remove-Item -Force $tmp
        }
    }
}

Write-Host "[1/10] Checking required commands..." -ForegroundColor Cyan
Test-CommandAvailable "ssh"
Test-CommandAvailable "scp"
Test-CommandAvailable "tar"
Test-CommandAvailable "git"

$mobileDir = Join-Path $ProjectRoot "mobile"
$buildWebDir = Join-Path $mobileDir "build/web"
$backendDir = Join-Path $ProjectRoot "backend"

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}

Push-Location $ProjectRoot
try {
    $srcCommit = (git rev-parse HEAD).Trim()
}
finally {
    Pop-Location
}

$deployHost = $env:COMPUTERNAME
if (-not $deployHost) { $deployHost = "unknown-host" }
$tsUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

if ($DeployMode -eq "Git" -and -not $SkipBackendDeploy) {
    Write-Host "DeployMode=Git: backend will be updated via git in $RemoteAppRoot (requires .git on server)." -ForegroundColor Cyan
}

if (-not $SkipWebDeploy -and -not $SkipWebBuild) {
    Write-Host "[2/10] Building Flutter web..." -ForegroundColor Cyan
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
    Write-Host "[2/10] Skip web build." -ForegroundColor Yellow
}

if (-not $SkipWebDeploy -and -not (Test-Path $buildWebDir)) {
    throw "Build output not found: $buildWebDir"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$localWebTar = Join-Path $mobileDir "web-$timestamp.tar.gz"
$localBackendTar = Join-Path $ProjectRoot "backend-$timestamp.tar.gz"
$remoteWebTar = "/tmp/web-$timestamp.tar.gz"
$remoteBackendTar = ""
if ($DeployMode -eq "Tar" -and -not $SkipBackendDeploy) {
    $remoteBackendTar = "/tmp/backend-$timestamp.tar.gz"
}

$webTarHash = ""
$backendTarHash = ""

try {
    if (-not $SkipWebDeploy) {
        Write-Host "[3/10] Packing web build..." -ForegroundColor Cyan
        if (Test-Path $localWebTar) {
            Remove-Item -Force $localWebTar
        }
        tar -C $buildWebDir -czf $localWebTar .
        if ($LASTEXITCODE -ne 0) { throw "tar web pack failed" }
        $webTarHash = (Get-FileHash $localWebTar -Algorithm SHA256).Hash.ToLower()
    }
    else {
        Write-Host "[3/10] Skip web package/deploy." -ForegroundColor Yellow
    }

    if ($DeployMode -eq "Tar" -and -not $SkipBackendDeploy) {
        Write-Host "[4/10] Packing backend source..." -ForegroundColor Cyan
        if (Test-Path $localBackendTar) {
            Remove-Item -Force $localBackendTar
        }
        # Exclude **all** DB/SQLite under backend/ — a nested *.db in the tar would overwrite prod data.
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
            --exclude "backend/**/*.db" `
            --exclude "backend/**/*.sqlite" `
            --exclude "backend/**/*.sqlite3" `
            --exclude "backend/.mypy_cache" `
            backend
        if ($LASTEXITCODE -ne 0) { throw "tar backend pack failed" }
        $backendTarHash = (Get-FileHash $localBackendTar -Algorithm SHA256).Hash.ToLower()
    }
    elseif ($DeployMode -eq "Git") {
        Write-Host "[4/10] Skip backend tar (Git mode)." -ForegroundColor Yellow
    }
    else {
        Write-Host "[4/10] Skip backend package/deploy." -ForegroundColor Yellow
    }

    Write-Host "[5/10] Uploading packages to $remote..." -ForegroundColor Cyan
    if (-not $SkipWebDeploy) {
        $c = Invoke-DeployScp -SshOpts $SshOpts -Source $localWebTar -Destination "${remote}:$remoteWebTar"
        if ($c -ne 0) {
            Write-SshAuthDeniedHint -Step "scp web tar" -RemoteTarget $remote -KeyPath $IdentityFile
            throw "scp web upload failed"
        }
    }
    if ($DeployMode -eq "Tar" -and -not $SkipBackendDeploy) {
        $c = Invoke-DeployScp -SshOpts $SshOpts -Source $localBackendTar -Destination "${remote}:$remoteBackendTar"
        if ($c -ne 0) {
            Write-SshAuthDeniedHint -Step "scp backend tar" -RemoteTarget $remote -KeyPath $IdentityFile
            throw "scp backend upload failed"
        }
    }

    Write-Host "[6/10] Publishing on server..." -ForegroundColor Cyan
    $doWeb = if ($SkipWebDeploy) { "0" } else { "1" }
    $doBackend = if ($SkipBackendDeploy) { "0" } else { "1" }
    $doRestart = if ($SkipBackendRestart) { "0" } else { "1" }
    $modeLower = $DeployMode.ToLower()
    $gitRefEsc = $GitRef.Replace("'", "'\''")

    $remoteScriptTemplate = @'
set -Eeuo pipefail
trap 'echo "[remote][ERROR] line=$LINENO cmd=$BASH_COMMAND" >&2' ERR

DO_WEB='__DO_WEB__'
DO_BACKEND='__DO_BACKEND__'
DO_RESTART='__DO_RESTART__'
DEPLOY_MODE='__DEPLOY_MODE__'
GIT_BRANCH='__GIT_BRANCH__'
GIT_REF='__GIT_REF__'
REMOTE_WEB_ROOT='__REMOTE_WEB_ROOT__'
REMOTE_APP_ROOT='__REMOTE_APP_ROOT__'
REMOTE_WEB_TAR='__REMOTE_WEB_TAR__'
REMOTE_BACKEND_TAR='__REMOTE_BACKEND_TAR__'
BACKEND_SERVICE='__BACKEND_SERVICE__'
BACKEND_HEALTH_URL='__BACKEND_HEALTH_URL__'
MANIFEST_SOURCE_COMMIT='__MANIFEST_SOURCE_COMMIT__'
MANIFEST_WEB_SHA='__MANIFEST_WEB_SHA__'
MANIFEST_BACKEND_SHA='__MANIFEST_BACKEND_SHA__'
MANIFEST_TS='__MANIFEST_TS__'
MANIFEST_HOST='__MANIFEST_HOST__'
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
    if [ "$DEPLOY_MODE" = "git" ]; then
        echo "[remote] Git update under $REMOTE_APP_ROOT"
        if [ ! -d "$REMOTE_APP_ROOT/.git" ]; then
            echo "[remote][ERROR] not a git clone: $REMOTE_APP_ROOT (init with: git clone <url> $REMOTE_APP_ROOT)" >&2
            exit 19
        fi
        cd "$REMOTE_APP_ROOT"
        git remote -v
        git fetch origin
        if [ -n "$GIT_REF" ]; then
            git checkout "$GIT_REF"
        else
            git checkout "$GIT_BRANCH"
            git pull --ff-only origin "$GIT_BRANCH"
        fi
    else
        BACKEND_DIR="$REMOTE_APP_ROOT/backend"
        SAVE_ROOT="/var/lib/clothing-assistant"
        STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
        PRESERVE_TAR=""
        if [ -d "$BACKEND_DIR" ]; then
            echo "[remote] Preserving backend state: .env, uploads/, *.db/*.sqlite* under $BACKEND_DIR"
            mkdir -p "$SAVE_ROOT"
            LIST="$(mktemp)"
            PRESERVE_TAR="$SAVE_ROOT/backend-data-$STAMP.tar.gz"
            (
              cd "$BACKEND_DIR" || exit 0
              : > "$LIST"
              [ -f .env ] && printf '%s\n' .env >> "$LIST"
              find uploads -type f 2>/dev/null >> "$LIST" || true
              find . -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) 2>/dev/null >> "$LIST" || true
              if [ -s "$LIST" ]; then
                if tar -czf "$PRESERVE_TAR" -T "$LIST"; then
                  echo "[remote] Snapshot: $PRESERVE_TAR ($(wc -l < "$LIST") paths)"
                else
                  rm -f "$PRESERVE_TAR"
                fi
              else
                rm -f "$PRESERVE_TAR"
              fi
            )
            rm -f "$LIST"
            if [ ! -f "$PRESERVE_TAR" ]; then PRESERVE_TAR=""; fi
        fi
        echo "[remote] Deploying backend tar to $REMOTE_APP_ROOT"
        mkdir -p "$REMOTE_APP_ROOT"
        tar -xzf "$REMOTE_BACKEND_TAR" -C "$REMOTE_APP_ROOT"
        if [ -n "$PRESERVE_TAR" ] && [ -f "$PRESERVE_TAR" ]; then
            echo "[remote] Restoring preserved .env / uploads / DB on top of deploy (prevents empty wardrobe)"
            mkdir -p "$BACKEND_DIR"
            tar -xzf "$PRESERVE_TAR" -C "$BACKEND_DIR"
        fi
    fi
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

echo "[remote] Writing RELEASE_MANIFEST"
if [ "$DEPLOY_MODE" = "git" ]; then
    mc="$(git -C "$REMOTE_APP_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    cat > "$REMOTE_APP_ROOT/RELEASE_MANIFEST" <<EOF
DEPLOY_MODE=git
SOURCE_GIT_COMMIT=$mc
WEB_BUILD_SHA256=$MANIFEST_WEB_SHA
BACKEND_PACKAGE_SHA256=
DEPLOY_TIME_UTC=$MANIFEST_TS
DEPLOY_FROM_HOST=$MANIFEST_HOST
EOF
else
    cat > "$REMOTE_APP_ROOT/RELEASE_MANIFEST" <<EOF
DEPLOY_MODE=tar
SOURCE_GIT_COMMIT=$MANIFEST_SOURCE_COMMIT
WEB_BUILD_SHA256=$MANIFEST_WEB_SHA
BACKEND_PACKAGE_SHA256=$MANIFEST_BACKEND_SHA
DEPLOY_TIME_UTC=$MANIFEST_TS
DEPLOY_FROM_HOST=$MANIFEST_HOST
EOF
fi

if [ -n "${REMOTE_WEB_TAR:-}" ] && [ -f "$REMOTE_WEB_TAR" ]; then
    rm -f "$REMOTE_WEB_TAR"
fi
if [ -n "${REMOTE_BACKEND_TAR:-}" ] && [ -f "$REMOTE_BACKEND_TAR" ]; then
    rm -f "$REMOTE_BACKEND_TAR"
fi
echo "Deploy finished"
'@

    $remoteScript = $remoteScriptTemplate
    $remoteScript = $remoteScript.Replace('__DO_WEB__', $doWeb)
    $remoteScript = $remoteScript.Replace('__DO_BACKEND__', $doBackend)
    $remoteScript = $remoteScript.Replace('__DO_RESTART__', $doRestart)
    $remoteScript = $remoteScript.Replace('__DEPLOY_MODE__', $modeLower)
    $remoteScript = $remoteScript.Replace('__GIT_BRANCH__', $GitBranch)
    $remoteScript = $remoteScript.Replace('__GIT_REF__', $gitRefEsc)
    $remoteScript = $remoteScript.Replace('__REMOTE_WEB_ROOT__', $RemoteWebRoot)
    $remoteScript = $remoteScript.Replace('__REMOTE_APP_ROOT__', $RemoteAppRoot)
    $remoteScript = $remoteScript.Replace('__REMOTE_WEB_TAR__', $remoteWebTar)
    $remoteScript = $remoteScript.Replace('__REMOTE_BACKEND_TAR__', $remoteBackendTar)
    $remoteScript = $remoteScript.Replace('__BACKEND_SERVICE__', $BackendService)
    $remoteScript = $remoteScript.Replace('__BACKEND_HEALTH_URL__', $BackendHealthUrl)
    $remoteScript = $remoteScript.Replace('__MANIFEST_SOURCE_COMMIT__', $srcCommit)
    $remoteScript = $remoteScript.Replace('__MANIFEST_WEB_SHA__', $webTarHash)
    $remoteScript = $remoteScript.Replace('__MANIFEST_BACKEND_SHA__', $backendTarHash)
    $remoteScript = $remoteScript.Replace('__MANIFEST_TS__', $tsUtc)
    $remoteScript = $remoteScript.Replace('__MANIFEST_HOST__', $deployHost)

    Invoke-RemoteBash -Remote $remote -ScriptText $remoteScript

    if ($VerifyLegacyHotfixMarkers) {
        Write-Host "[7/10] Verifying legacy hotfix markers on server..." -ForegroundColor Cyan
        $verifyScript = @"
set -e
grep -n "application/octet-stream" "$RemoteAppRoot/backend/app/api/smart_outfit.py" >/dev/null
grep -n "No outfit cards generated from wardrobe" "$RemoteAppRoot/backend/app/services/smart_outfit_generator.py" >/dev/null
echo "Backend hotfix markers found"
"@
        Invoke-RemoteBash -Remote $remote -ScriptText $verifyScript
    }
    else {
        Write-Host "[7/10] Skip legacy hotfix marker grep (use -VerifyLegacyHotfixMarkers to enable)." -ForegroundColor Yellow
    }
}
finally {
    Write-Host "[8/10] Cleaning local temporary packages..." -ForegroundColor Cyan
    if (Test-Path $localWebTar) {
        Remove-Item -Force $localWebTar
    }
    if (Test-Path $localBackendTar) {
        Remove-Item -Force $localBackendTar
    }
}

if (-not $SkipPostDeployVerify) {
    Write-Host "[9/10] Post-deploy verify (smoke + audit)..." -ForegroundColor Cyan
    $verifySh = Join-Path $ProjectRoot "deploy/ecs/post_deploy_verify.sh"
    $auditSh = Join-Path $ProjectRoot "scripts/full_chain_consistency_audit.sh"
    if (-not (Test-Path $verifySh)) { throw "Missing $verifySh" }
    if (-not (Test-Path $auditSh)) { throw "Missing $auditSh" }

    $c1 = Invoke-DeployScp -SshOpts $SshOpts -Source $verifySh -Destination "${remote}:/tmp/post_deploy_verify.sh"
    if ($c1 -ne 0) {
        Write-SshAuthDeniedHint -Step "scp post_deploy_verify.sh" -RemoteTarget $remote -KeyPath $IdentityFile
        throw "scp post_deploy_verify.sh failed"
    }
    $c2 = Invoke-DeployScp -SshOpts $SshOpts -Source $auditSh -Destination "${remote}:/tmp/full_chain_consistency_audit.sh"
    if ($c2 -ne 0) {
        Write-SshAuthDeniedHint -Step "scp full_chain_consistency_audit.sh" -RemoteTarget $remote -KeyPath $IdentityFile
        throw "scp full_chain_consistency_audit.sh failed"
    }

    $envAppRoot = $RemoteAppRoot.Replace("'", "'\''")
    $envWebRoot = $RemoteWebRoot.Replace("'", "'\''")
    $vCmd = "chmod +x /tmp/post_deploy_verify.sh /tmp/full_chain_consistency_audit.sh && APP_ROOT='$envAppRoot' WEB_ROOT='$envWebRoot' ENV_FILE='$envAppRoot/backend/.env' AUDIT_SCRIPT=/tmp/full_chain_consistency_audit.sh bash /tmp/post_deploy_verify.sh"
    $verifyOut = & ssh @SshOpts $remote $vCmd 2>&1
    $vCode = $LASTEXITCODE
    if ($verifyOut) {
        ($verifyOut | ForEach-Object { $_.ToString() }) | ForEach-Object { Write-Host $_ }
    }
    if ($vCode -ne 0) {
        throw "post_deploy_verify failed (exit=$vCode)"
    }
}
else {
    Write-Host "[9/10] Skip post-deploy verify (-SkipPostDeployVerify)." -ForegroundColor Yellow
}

Write-Host "[10/10] Done. Hard refresh browser with Ctrl+F5 if you deployed web." -ForegroundColor Green
