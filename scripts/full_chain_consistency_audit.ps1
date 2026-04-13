param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$IdentityFile = "",
    [string]$RemoteAppRoot = "/opt/clothing-assistant/clothing-assistant-main",
    [string]$RemoteWebRoot = "/usr/share/nginx/html",
    [string]$RemoteBackendEnv = "/opt/clothing-assistant/clothing-assistant-main/backend/.env",
    [string]$LocalApi = "http://127.0.0.1:8010/health",
    [string]$RemoteApi = "http://127.0.0.1:8010/health",
    [switch]$AutoFix,
    [switch]$SkipRemote
)

. (Join-Path $PSScriptRoot "DeployCommon.ps1")
$script:SshOptsAudit = Get-DeploySshOpts -IdentityFile $IdentityFile

$ErrorActionPreference = "Stop"

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )
    $script:Results += [pscustomobject]@{
        Name = $Name
        Status = $Status
        Detail = $Detail
    }
}

function Invoke-SshSafe {
    param([string]$Command)
    $all = $script:SshOptsAudit + @("$User@$ServerHost", $Command)
    $oldEA = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $out = & ssh @all 2>&1
        $code = $LASTEXITCODE
        return @($code, ($out | Out-String).Trim())
    }
    finally {
        $ErrorActionPreference = $oldEA
    }
}

function Get-EnvKeys {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    $keys = @()
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line) { return }
        if ($line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -gt 0) {
            $keys += $line.Substring(0, $idx).Trim()
        }
    }
    return $keys | Sort-Object -Unique
}

$script:Results = @()
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location $projectRoot
try {
    $localCommit = (git rev-parse HEAD).Trim()
    Add-Result "code.local.commit" "ok" $localCommit

    $webBuildPath = Join-Path $projectRoot "mobile/build/web/index.html"
    if (Test-Path $webBuildPath) {
        $hash = (Get-FileHash $webBuildPath -Algorithm SHA256).Hash
        Add-Result "frontend.local.build" "ok" "mobile/build/web/index.html sha256=$hash"
    } else {
        Add-Result "frontend.local.build" "warn" "missing mobile/build/web/index.html"
    }

    $localEnvExample = Join-Path $projectRoot "backend/.env.example"
    $localEnvKeys = Get-EnvKeys -Path $localEnvExample
    Add-Result "backend.local.env.keys" "ok" ("count=" + $localEnvKeys.Count)

    try {
        $resp = Invoke-RestMethod -Method Get -Uri $LocalApi -TimeoutSec 5
        Add-Result "backend.local.health" "ok" ($resp | ConvertTo-Json -Compress)
    } catch {
        Add-Result "backend.local.health" "warn" "Local health check failed: $($_.Exception.Message)"
    }

    if (-not $SkipRemote) {
        $sshCheck = Invoke-SshSafe "echo remote-ok"
        if ($sshCheck[0] -ne 0) {
            Add-Result "remote.connectivity" "fail" "SSH unavailable: $($sshCheck[1])"
        } else {
            Add-Result "remote.connectivity" "ok" $sshCheck[1]

            $remoteCommit = Invoke-SshSafe "cd '$RemoteAppRoot'; git rev-parse HEAD"
            if ($remoteCommit[0] -eq 0) {
                $remoteCommitText = $remoteCommit[1].Trim()
                $status = if ($remoteCommitText -eq $localCommit) { "ok" } else { "fail" }
                Add-Result "code.remote.commit" $status "remote=$remoteCommitText local=$localCommit"
            } else {
                Add-Result "code.remote.commit" "warn" $remoteCommit[1]
            }

            $remoteIndexHash = Invoke-SshSafe "sha256sum '$RemoteWebRoot/index.html' | awk '{print `$1}'"
            if ($remoteIndexHash[0] -eq 0 -and (Test-Path $webBuildPath)) {
                $localIndexHash = (Get-FileHash $webBuildPath -Algorithm SHA256).Hash.ToLower()
                $rh = $remoteIndexHash[1].Trim().ToLower()
                $status = if ($rh -eq $localIndexHash) { "ok" } else { "fail" }
                Add-Result "frontend.remote.index" $status "remote=$rh local=$localIndexHash"
            } else {
                Add-Result "frontend.remote.index" "warn" $remoteIndexHash[1]
            }

            $remoteEnvDump = Invoke-SshSafe "if [ -f '$RemoteBackendEnv' ]; then grep -v '^#' '$RemoteBackendEnv' | grep '='; fi"
            if ($remoteEnvDump[0] -eq 0) {
                $tmpFile = [System.IO.Path]::GetTempFileName()
                Set-Content -Path $tmpFile -Value $remoteEnvDump[1] -Encoding UTF8
                $remoteKeys = Get-EnvKeys -Path $tmpFile
                Remove-Item -Force $tmpFile

                $missing = @($localEnvKeys | Where-Object { $_ -notin $remoteKeys })
                $status = if ($missing.Count -eq 0) { "ok" } else { "fail" }
                $detail = if ($missing.Count -eq 0) {
                    "remote env keys cover local example keys"
                } else {
                    "missing keys: " + ($missing -join ",")
                }
                Add-Result "backend.remote.env.keys" $status $detail
            } else {
                Add-Result "backend.remote.env.keys" "warn" $remoteEnvDump[1]
            }

            $remoteHealth = Invoke-SshSafe "curl -fsS '$RemoteApi'"
            if ($remoteHealth[0] -eq 0) {
                Add-Result "backend.remote.health" "ok" $remoteHealth[1]
            } else {
                Add-Result "backend.remote.health" "fail" $remoteHealth[1]
            }
        }
    } else {
        Add-Result "remote.connectivity" "skip" "SkipRemote enabled"
    }

    if ($AutoFix) {
        $deployScript = Join-Path $projectRoot "scripts/deploy_full_to_ecs.ps1"
        if (Test-Path $deployScript) {
            Add-Result "autofix.deploy" "info" "running deploy_full_to_ecs.ps1"
            & powershell -ExecutionPolicy Bypass -File $deployScript
            if ($LASTEXITCODE -eq 0) {
                Add-Result "autofix.deploy" "ok" "deploy completed"
            } else {
                Add-Result "autofix.deploy" "fail" "deploy script exit=$LASTEXITCODE"
            }
        } else {
            Add-Result "autofix.deploy" "fail" "missing scripts/deploy_full_to_ecs.ps1"
        }
    }
}
finally {
    Pop-Location
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "=== Full-Chain Consistency Audit @ $ts ==="
$Results | ForEach-Object {
    Write-Host ("[{0}] {1} :: {2}" -f $_.Status.ToUpper(), $_.Name, $_.Detail)
}

$failCount = @($Results | Where-Object { $_.Status -eq "fail" }).Count
$warnCount = @($Results | Where-Object { $_.Status -eq "warn" }).Count
Write-Host "Summary: fail=$failCount warn=$warnCount total=$($Results.Count)"

if ($failCount -gt 0) { exit 2 }
if ($warnCount -gt 0) { exit 1 }
exit 0
