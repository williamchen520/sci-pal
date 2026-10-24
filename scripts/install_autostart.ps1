# SciPal watchdog autostart installer (Stage 4-A)
# NOTE: ASCII-only file on purpose - avoids Windows console encoding problems.
#
# What this script does:
#   1. Creates a Windows Scheduled Task named "SciPalWatchdog"
#   2. Trigger : AT LOGON, delayed 00:00:30 (avoids logon resource contention)
#   3. Action  : run scripts/sciPal_watchdog.py with the project venv python
#   4. Idempotent: removes an existing task with the same name before creating
#
# It does NOT install packages, does NOT touch SciPal business code,
# and does NOT start Flask directly - the watchdog decides when to launch it.

$ErrorActionPreference = "Stop"

$TaskName    = "SciPalWatchdog"
$ProjectRoot = "D:\sciPal"
$VenvPython  = "$ProjectRoot\venv_sciPal_py312\Scripts\python.exe"
$Script      = "$ProjectRoot\scripts\sciPal_watchdog.py"

Write-Host "=== SciPal watchdog autostart installer ==="
Write-Host "Task name    : $TaskName"
Write-Host "Trigger      : AT LOGON (delay 00:00:30)"
Write-Host "Command      : `"$VenvPython`" `"$Script`""
Write-Host ""
Write-Host "This creates a Windows Scheduled Task (a system-state change)."

$answer = Read-Host "Proceed? (y/N)"
if ($answer -notmatch '^(y|Y)$') {
    Write-Host "Aborted. No change was made."
    exit 0
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: venv python not found: $VenvPython"
    exit 1
}
if (-not (Test-Path $Script)) {
    Write-Host "ERROR: watchdog script not found: $Script"
    exit 1
}

schtasks /Query /TN $TaskName > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Existing task found - removing it first (idempotent reinstall)..."
    schtasks /Delete /TN $TaskName /F
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: failed to remove the existing task."
        exit 1
    }
}

$action = "`"$VenvPython`" `"$Script`""
schtasks /Create /TN $TaskName /TR $action /SC ONLOGON /DELAY 0000:30 /RL HIGHEST /F
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: failed to create the task."
    exit 1
}

Write-Host ""
Write-Host "Task created."
Write-Host "Verify : schtasks /Query /TN $TaskName /V /FO LIST"
Write-Host "Run now : schtasks /Run /TN $TaskName"
Write-Host "Remove  : powershell -File $ProjectRoot\scripts\uninstall_autostart.ps1"
