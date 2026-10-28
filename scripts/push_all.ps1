# Push branches to GitHub (main) and Gitee (mirror)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/push_all.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "==> GitHub: DSH-dev"
git -C $repo push github DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push github DSH-dev failed" }

Write-Host "==> GitHub: dev / master"
git -C $repo push github dev master
if ($LASTEXITCODE -ne 0) { throw "push github dev/master failed" }

Write-Host "==> Gitee mirror: dev / master / DSH-dev"
git -C $repo push origin dev master DSH-dev
if ($LASTEXITCODE -ne 0) { throw "push gitee mirror failed" }

Write-Host "done"
