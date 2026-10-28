# Install git pre-push hook (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/install_git_hooks.ps1

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

git -C $repo config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { throw "git config failed" }

# Mark executable in the index (keeps exec bit across platforms)
git -C $repo add --chmod=+x .githooks/pre-push

Write-Host "core.hooksPath=.githooks"
Write-Host "Protected branches: dev / master (block force-push and delete)"
Write-Host "Bypass (not recommended): git push --no-verify"
