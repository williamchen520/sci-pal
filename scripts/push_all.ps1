# Push branches to GitHub (main) and Gitee (mirror)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/push_all.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "==> GitHub: DSH-dev"
git -C $repo push github DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push github DSH-dev failed" }

Write-Host "==> Gitee mirror: dev / master (GitHub dev/master are protected; merge via PR first)"
git -C $repo push origin dev master
if ($LASTEXITCODE -ne 0) { throw "push gitee dev/master failed" }

Write-Host "==> Gitee mirror: DSH-dev"
git -C $repo push origin DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push gitee mirror failed" }

Write-Host "done"
