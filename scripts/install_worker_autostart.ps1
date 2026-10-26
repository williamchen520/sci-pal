# SciPal resident worker autostart installer.
# NOTE: ASCII-only file on purpose - avoids Windows console encoding problems.
#
# Registers a Windows Scheduled Task "SciPalWorker":
#   Trigger : AT LOGON, delayed 30 seconds
#   Action  : <venv python> -m services.workflow.worker --queue-dir <root>\data\runs\_queue
#             stdout/stderr appended to logs\worker.log
#   RunLevel: Limited (normal user rights)
#
# Usage:
#   powershell -File scripts\install_worker_autostart.ps1          (asks first)
#   powershell -File scripts\install_worker_autostart.ps1 -Force   (no prompt)
#
# Remove with:
#   Unregister-ScheduledTask -TaskName SciPalWorker -Confirm:$false

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$TaskName = "SciPalWorker"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython  = Join-Path $ProjectRoot "venv_sciPal_py312\Scripts\python.exe"
$QueueDir    = Join-Path $ProjectRoot "data\runs\_queue"
$LogDir      = Join-Path $ProjectRoot "logs"
$LogFile     = Join-Path $LogDir "worker.log"

Write-Host "=== SciPal worker autostart installer ==="
Write-Host "Task name : $TaskName"
Write-Host "Trigger   : AT LOGON (delay 30s)"
Write-Host "Queue dir : $QueueDir"
Write-Host "Log file  : $LogFile"
Write-Host ""

if ($Force) {
    Write-Host "-Force specified - skipping confirmation."
} else {
    $answer = Read-Host "Proceed? (y/N)"
    if ($answer -notmatch '^(y|Y)$') {
        Write-Host "Aborted. No change was made."
        exit 0
    }
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: venv python not found: $VenvPython"
    exit 1
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

try {
    Import-Module ScheduledTasks -ErrorAction Stop

    $inner = "-m services.workflow.worker --queue-dir `"$QueueDir`" --log-file `"$LogFile`""
    $action = New-ScheduledTaskAction -Execute $VenvPython `
        -Argument $inner `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT30S"

    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "SciPal resident worker (workflow + ingest queue)" `
        -Force | Out-Null

    Write-Host "OK: scheduled task '$TaskName' registered."
} catch {
    Write-Host "ERROR: failed to register scheduled task: $($_.Exception.Message)"
    Write-Host "Fallback: run the worker manually in a terminal:"
    Write-Host "  $VenvPython -m services.workflow.worker --queue-dir `"$QueueDir`""
    exit 1
}
