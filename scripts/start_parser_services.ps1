<#
.SYNOPSIS
    Ensure SciPal parser services are running:
      - GROBID CRF   (container, 8070)
      - GROBID Full  (container, 8071, optional)
      - MinerU API   (mineru-api, 8000)
      - MinerU server (document center, required by the CLI)

.DESCRIPTION
    Idempotent: checks health first, only starts what is missing.
    Run at logon via Task Scheduler or manually after reboot.

.PARAMETER SkipFull
    Do not start the 37 GB GROBID full container.

.PARAMETER CheckOnly
    Only report status; never start anything.

.PARAMETER MineruHome
    Model directory for MinerU (default D:\mineru_home). Must be consistent
    with the MINERU_HOME seen by mineru-api and mineru CLI.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_parser_services.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipFull,
    [switch]$CheckOnly,
    [string]$MineruHome = "D:\mineru_home"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$venvScripts = Join-Path $repo "venv_sciPal_py312\Scripts"
$mineruExe = Join-Path $venvScripts "mineru.exe"
$mineruApiExe = Join-Path $venvScripts "mineru-api.exe"

$env:MINERU_HOME = $MineruHome
$results = @()

function Test-Http([string]$Url, [int]$TimeoutSec = 3) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

function Wait-Http([string]$Url, [int]$Seconds = 180) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Http $Url 3) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Add-Result([string]$Name, [bool]$Ok, [string]$Detail) {
    $script:results += [pscustomobject]@{ Service = $Name; Ok = $Ok; Detail = $Detail }
}

function Ensure-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Add-Result "docker" $false "docker CLI not found"
        return $false
    }
    $ok = $false
    try { docker info *> $null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
    if ($ok) { return $true }
    if ($CheckOnly) {
        Add-Result "docker" $false "daemon not running"
        return $false
    }
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Start-Process -FilePath $desktop -WindowStyle Hidden
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 5
            try { docker info *> $null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
            if ($ok) { return $true }
        }
    }
    Add-Result "docker" $false "daemon did not start"
    return $false
}

function Ensure-Grobid([string]$Name, [string]$Image, [int]$HostPort) {
    $alive = "http://127.0.0.1:$HostPort/api/isalive"
    if (Test-Http $alive 3) {
        Add-Result $Name $true "already alive on $HostPort"
        return
    }
    if ($CheckOnly) {
        Add-Result $Name $false "not responding on $HostPort"
        return
    }
    $exists = $false
    try { docker inspect $Name *> $null; $exists = ($LASTEXITCODE -eq 0) } catch { $exists = $false }
    if ($exists) {
        try { docker start $Name *> $null } catch { }
    } else {
        try { docker run -d --name $Name --restart unless-stopped -p "${HostPort}:8070" $Image *> $null } catch { }
    }
    if (Wait-Http $alive 180) {
        Add-Result $Name $true "started on $HostPort"
    } else {
        Add-Result $Name $false "started but health check failed on $HostPort"
    }
}

function Ensure-MineruApi {
    $url = "http://127.0.0.1:8000/openapi.json"
    if (Test-Http $url 3) {
        Add-Result "mineru-api" $true "already alive on 8000"
        return
    }
    if ($CheckOnly) {
        Add-Result "mineru-api" $false "not responding on 8000"
        return
    }
    if (-not (Test-Path $mineruApiExe)) {
        Add-Result "mineru-api" $false "missing $mineruApiExe"
        return
    }
    Start-Process -FilePath $mineruApiExe `
        -ArgumentList "--tier", "basic", "--port", "8000" `
        -WindowStyle Hidden
    if (Wait-Http $url 240) {
        Add-Result "mineru-api" $true "started on 8000"
    } else {
        Add-Result "mineru-api" $false "started but health check failed on 8000"
    }
}

function Ensure-MineruServer {
    if (-not (Test-Path $mineruExe)) {
        Add-Result "mineru-server" $false "missing $mineruExe"
        return
    }
    $status = & $mineruExe server status 2>&1 | Out-String
    if ($status -match "running|Running|PID") {
        Add-Result "mineru-server" $true "already running"
        return
    }
    if ($CheckOnly) {
        Add-Result "mineru-server" $false "not running"
        return
    }
    & $mineruExe server start *> $null
    Start-Sleep -Seconds 10
    $status = & $mineruExe server status 2>&1 | Out-String
    if ($status -match "running|Running|PID") {
        Add-Result "mineru-server" $true "started"
    } else {
        Add-Result "mineru-server" $false "start command returned but status is not running"
    }
}

# ---------------------------------------------------------------- main
if (Ensure-Docker) {
    Ensure-Grobid "grobid-crf" "lfoppiano/grobid:latest-crf" 8070
    if (-not $SkipFull) {
        Ensure-Grobid "grobid-full" "grobid/grobid:0.9.1-full" 8071
    }
}
Ensure-MineruApi
Ensure-MineruServer

$results | Format-Table -AutoSize

$failed = @($results | Where-Object { -not $_.Ok })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "FAILED: $($failed.Service -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "All parser services are healthy." -ForegroundColor Green
exit 0
