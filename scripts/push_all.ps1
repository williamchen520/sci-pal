# Push branches to GitHub (main) and Gitee (mirror)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/push_all.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

function Invoke-GitWithRetry {
    param(
        [string[]]$GitArgs,
        [string]$Label,
        [int]$Attempts = 3
    )
    for ($i = 1; $i -le $Attempts; $i++) {
        & git -C $repo @GitArgs
        if ($LASTEXITCODE -eq 0) { return }
        if ($i -lt $Attempts) {
            $wait = 5 * $i
            Write-Warning "$Label failed (attempt $i/$Attempts); retry in ${wait}s"
            Start-Sleep -Seconds $wait
        }
    }
    throw "$Label failed after $Attempts attempts"
}

Write-Host "==> fetch GitHub"
Invoke-GitWithRetry -GitArgs @("fetch", "github") -Label "fetch github"

Write-Host "==> GitHub: DSH-dev"
Invoke-GitWithRetry -GitArgs @("push", "github", "DSH-dev") -Label "push github DSH-dev"

Write-Host "==> Gitee mirror: dev / master / DSH-dev (use GitHub refs, not stale local branches)"
Invoke-GitWithRetry -GitArgs @(
    "push", "origin",
    "github/dev:dev", "github/dev:master", "github/DSH-dev:DSH-dev"
) -Label "push gitee mirror"

Write-Host "done"
