# Free TCP port 8000 (Option A).
# Usage (repo root):  powershell -ExecutionPolicy Bypass -File .\scripts\free-port-8000.ps1
# If normal run cannot kill listeners, script will prompt UAC and retry as Administrator.

param(
    [switch] $Elevated
)

$ErrorActionPreference = 'Continue'

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$isAdmin = Test-IsAdmin
Write-Host "Finding LISTEN processes on port 8000..." -ForegroundColor Cyan
if ($Elevated) { Write-Host "(elevated)" -ForegroundColor Green }
elseif ($isAdmin) { Write-Host "(running as Administrator)" -ForegroundColor Green }

$pids = @()
try {
    $pids = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue |
        ForEach-Object { $_.OwningProcess } |
        Sort-Object -Unique
} catch { }

if (-not $pids -or $pids.Count -eq 0) {
    Write-Host "No listener on 8000 (port is free)." -ForegroundColor Green
    exit 0
}

Write-Host "Stopping PIDs: $($pids -join ', ')" -ForegroundColor Yellow

foreach ($procId in $pids) {
    $stopped = $false
    try {
        $p = Get-Process -Id $procId -ErrorAction Stop
        Write-Host "  PID $procId : $($p.ProcessName)"
        Stop-Process -Id $procId -Force
        Write-Host "  Stopped $procId" -ForegroundColor Green
        $stopped = $true
    } catch {
        Write-Host "  Stop-Process failed for $procId, trying taskkill..." -ForegroundColor Yellow
    }
    if (-not $stopped) {
        & taskkill.exe /F /PID $procId 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  taskkill stopped $procId" -ForegroundColor Green
            $stopped = $true
        }
    }
}

Start-Sleep -Milliseconds 600

$still = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
if ($still.Count -gt 0 -and -not $Elevated -and -not $isAdmin) {
    Write-Host ""
    Write-Host "Port 8000 still in use. Requesting Administrator (UAC)..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $scriptPath,
        '-Elevated'
    )
    exit 0
}

Write-Host ""
Write-Host "Port 8000 after kill:" -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Format-Table -AutoSize

$final = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
if ($final.Count -gt 0) {
    Write-Host ""
    Write-Host "Still listening. Open Task Manager -> Details, end these PIDs manually:" -ForegroundColor Red
    $final | ForEach-Object { Write-Host "  PID $($_.OwningProcess)" }
}
