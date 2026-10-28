# Push branches to GitHub (main) and Gitee (mirror)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/push_all.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "==> fetch GitHub"
git -C $repo fetch github
if ($LASTEXITCODE -ne 0) { throw "fetch github failed" }

Write-Host "==> GitHub: DSH-dev"
git -C $repo push github DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push github DSH-dev failed" }

Write-Host "==> Gitee mirror: dev / master / DSH-dev (use GitHub refs, not stale local branches)"
git -C $repo push origin github/dev:dev github/dev:master github/DSH-dev:DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push gitee mirror failed" }

Write-Host "done"
