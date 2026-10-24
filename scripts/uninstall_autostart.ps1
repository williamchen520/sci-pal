# SciPal watchdog autostart uninstaller (Stage 4-A)
# NOTE: ASCII-only file on purpose - avoids Windows console encoding problems.
#
# What this script does:
#   1. Deletes the Windows Scheduled Task named "SciPalWatchdog"
#   2. Does NOT stop any already-running watchdog or Flask process
#      (kill them manually if needed)

$ErrorActionPreference = "Stop"

$TaskName = "SciPalWatchdog"

Write-Host "=== SciPal watchdog autostart uninstaller ==="
Write-Host "This will DELETE the Windows Scheduled Task named: $TaskName"

$answer = Read-Host "Proceed? (y/N)"
if ($answer -notmatch '^(y|Y)$') {
    Write-Host "Aborted. No change was made."
    exit 0
}

schtasks /Query /TN $TaskName > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Task not found: $TaskName - nothing to do."
    exit 0
}

schtasks /Delete /TN $TaskName /F
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: failed to delete the task."
    exit 1
}

Write-Host ""
Write-Host "Task deleted."
Write-Host "Note: a watchdog process started by this task may still be running."
Write-Host "To stop it: find its PID in logs/sciPal_watchdog.lock and stop that process."
