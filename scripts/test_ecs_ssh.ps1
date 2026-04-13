#requires -Version 5.1
<#
.SYNOPSIS
  Diagnose SSH key login to ECS before running deploy_full_to_ecs.ps1.

.EXAMPLE
  .\scripts\test_ecs_ssh.ps1 -ServerHost "101.200.127.179" -User root -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519"
  .\scripts\test_ecs_ssh.ps1 -VerboseSsh
#>
param(
    [string]$ServerHost = "101.200.127.179",
    [string]$User = "root",
    [string]$IdentityFile = "",
    [switch]$VerboseSsh
)

$ErrorActionPreference = "Stop"

if (-not $IdentityFile) {
    $IdentityFile = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
}

if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "Private key not found: $IdentityFile"
}

$keyPath = (Resolve-Path -LiteralPath $IdentityFile).Path
Write-Host "Private key: $keyPath" -ForegroundColor Cyan
Write-Host "ACL (if too open, OpenSSH on Windows may ignore this key):" -ForegroundColor DarkGray
& icacls.exe $keyPath 2>$null | ForEach-Object { Write-Host "  $_" }

Write-Host "Public key fingerprint (must match ECS key pair / line in authorized_keys):" -ForegroundColor DarkGray
& ssh-keygen.exe -l -E sha256 -f $keyPath 2>&1 | ForEach-Object { Write-Host "  $_" }

$remote = "${User}@${ServerHost}"
Write-Host "Testing: $remote (BatchMode=yes, same as deploy script)..." -ForegroundColor Cyan

$sshArgs = New-Object System.Collections.Generic.List[string]
if ($VerboseSsh) {
    $sshArgs.Add("-vv")
}
$sshArgs.Add("-i")
$sshArgs.Add($keyPath)
$sshArgs.Add("-o")
$sshArgs.Add("BatchMode=yes")
$sshArgs.Add("-o")
$sshArgs.Add("StrictHostKeyChecking=accept-new")
$sshArgs.Add("-o")
$sshArgs.Add("ConnectTimeout=15")
$sshArgs.Add($remote)
$sshArgs.Add("echo ok; whoami; hostname")

$argv = $sshArgs.ToArray()
& ssh @argv
$code = $LASTEXITCODE

if ($code -ne 0) {
    Write-Host ""
    Write-Host "FAILED (exit=$code). Common causes:" -ForegroundColor Red
    Write-Host "  1) Public key not in this user's ~/.ssh/authorized_keys on the server."
    Write-Host "  2) Wrong -User: Alibaba images may use 'ecs-user' not 'root'."
    Write-Host "  3) Windows key ACL too loose — try (adjust path):"
    Write-Host "     icacls `"$keyPath`" /inheritance:r"
    Write-Host "     icacls `"$keyPath`" /grant:r `"${env:USERNAME}:(R)`""
    Write-Host "     icacls `"$keyPath`" /grant `"SYSTEM:(R)`""
    Write-Host "  4) .pub on server does not match this private key (ssh-keygen -y -f key to compare)."
    Write-Host "  5) Alibaba: instance key pair is NOT this file — use the .pem you downloaded for that pair,"
    Write-Host "     or use Workbench/VNC to append your id_ed25519.pub to ~/.ssh/authorized_keys."
    Write-Host "Re-run with -VerboseSsh for OpenSSH client debug output."
    exit $code
}

Write-Host "SSH OK — run deploy_full_to_ecs.ps1 with same -User and -IdentityFile." -ForegroundColor Green
exit 0
