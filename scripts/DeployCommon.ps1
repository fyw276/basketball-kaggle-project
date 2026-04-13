# Shared SSH/SCP options for non-interactive deploy & audit (key-based auth).
# Usage: dot-source from deploy_full_to_ecs.ps1 / push_and_run_remote_audit.ps1

function Get-DeploySshOpts {
    param(
        [string]$IdentityFile = ""
    )
    $opts = New-Object System.Collections.Generic.List[string]
    if ($IdentityFile -and (Test-Path -LiteralPath $IdentityFile)) {
        $opts.Add("-i")
        $opts.Add((Resolve-Path -LiteralPath $IdentityFile).Path)
    }
    # BatchMode: no password prompt — requires SSH key or agent.
    $opts.Add("-o")
    $opts.Add("BatchMode=yes")
    $opts.Add("-o")
    $opts.Add("StrictHostKeyChecking=accept-new")
    $opts.Add("-o")
    $opts.Add("ConnectTimeout=20")
    return , $opts.ToArray()
}

function Invoke-DeployScp {
    param(
        [string[]]$SshOpts,
        [string]$Source,
        [string]$Destination
    )
    $all = $SshOpts + @($Source, $Destination)
    & scp @all
    return $LASTEXITCODE
}

function Invoke-DeploySsh {
    param(
        [string[]]$SshOpts,
        [string]$Remote, # user@host
        [string]$RemoteCommand
    )
    $all = $SshOpts + @($Remote, $RemoteCommand)
    & ssh @all
    return $LASTEXITCODE
}
