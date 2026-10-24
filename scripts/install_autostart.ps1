# SciPal watchdog autostart installer (Stage 4-A / revised)
# NOTE: ASCII-only file on purpose - avoids Windows console encoding problems.
#
# What this script does:
#   1. Registers a Windows Scheduled Task named "SciPalWatchdog"
#   2. Trigger : AT LOGON, delayed 30 seconds
#   3. Action  : run scripts/sciPal_watchdog.py with the project venv python
#   4. RunLevel: Limited (normal user rights, no elevation)
#   5. ExecutionTimeLimit = PT0S (unlimited) - prevents Windows from
#      force-terminating the task after the default 3 days
#
# Paths are derived from this script's location - no hardcoded project path.
#
# Usage:
#   powershell -File scripts\install_autostart.ps1          (asks for confirmation)
#   powershell -File scripts\install_autostart.ps1 -Force   (no prompt, for automation)
#
# It does NOT install packages, does NOT touch SciPal business code,
# and does NOT start Flask directly - the watchdog decides when to launch it.

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$TaskName = "SciPalWatchdog"

# Derive paths from the script location (scripts\ -> project root)
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPython  = Join-Path $ProjectRoot "venv_sciPal_py312\Scripts\python.exe"
$Watchdog    = Join-Path $ProjectRoot "scripts\sciPal_watchdog.py"
$Uninstaller = Join-Path $ProjectRoot "scripts\uninstall_autostart.ps1"

Write-Host "=== SciPal watchdog autostart installer ==="
Write-Host "Task name        : $TaskName"
Write-Host "Trigger          : AT LOGON (delay 30s)"
Write-Host "Command          : `"$VenvPython`" `"$Watchdog`""
Write-Host "Working dir      : $ProjectRoot"
Write-Host "RunLevel         : Limited (no elevation)"
Write-Host "ExecutionTimeLimit: PT0S (unlimited, no 3-day kill)"
Write-Host ""
Write-Host "This registers a Windows Scheduled Task (a system-state change)."

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
if (-not (Test-Path $Watchdog)) {
    Write-Host "ERROR: watchdog script not found: $Watchdog"
    exit 1
}

try {
    Import-Module ScheduledTasks -ErrorAction Stop

    $action = New-ScheduledTaskAction -Execute $VenvPython `
        -Argument ("`"{0}`"" -f $Watchdog) `
        -WorkingDirectory $ProjectRoot

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger.Delay = "PT30S"

    # ExecutionTimeLimit PT0S = no time limit (default is PT72H, which silently
    # terminates long-running browser tasks after 3 days).
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
        -Force | Out-Null
} catch {
    Write-Host "ERROR: failed to register the scheduled task."
    Write-Host $_.Exception.Message
    Write-Host ""
    Write-Host "If this is a permission problem, try running PowerShell as Administrator,"
    Write-Host "or use the fallback: schtasks /Create /TN $TaskName /TR `"`"$VenvPython`" `"$Watchdog`"`" /SC ONLOGON /DELAY 0000:30 /RL LIMITED /F"
    exit 1
}

Write-Host ""
Write-Host "Task registered."

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "RunLevel          : $($task.Principal.RunLevel)"
Write-Host "ExecutionTimeLimit: $($task.Settings.ExecutionTimeLimit)"
Write-Host ""
Write-Host "Verify : Get-ScheduledTask -TaskName $TaskName | Select-Object *"
Write-Host "Run now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Remove : powershell -File $Uninstaller"
