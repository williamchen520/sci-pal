# Apply the SciPal MCP patch to the DSH desktop profile.
# ASCII-only on purpose: avoids Windows console encoding corruption.
#
# Usage (PowerShell):  & "D:\sciPal\tests\apply_dsh_patch.ps1"
#
# It refuses to run while DSH is up, backs up first, then verifies the result.

$ErrorActionPreference = 'Stop'

$src = 'D:\sciPal\tests\cordis.patch.scipal.yml'
$dir = Join-Path $env:USERPROFILE '.dsh\profiles\desktop'
$dst = Join-Path $dir 'cordis.patch.yml'
$bak = Join-Path $dir ('cordis.patch.yml.' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.bak')

Write-Host '--- 0/3 precheck ---'
$running = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue
if ($running) {
    Write-Host 'FAIL: DSH is still running.' -ForegroundColor Red
    Write-Host 'Fully quit it first (system tray icon too), then re-run this script.'
    exit 1
}
Write-Host 'OK: DSH is not running.'

if (-not (Test-Path $src)) { Write-Host 'FAIL: source file missing: ' $src -ForegroundColor Red; exit 1 }
if (-not (Test-Path $dst)) { Write-Host 'FAIL: DSH profile not found: ' $dst -ForegroundColor Red; exit 1 }
Write-Host 'OK: source and profile present.'

Write-Host '--- 1/3 backup ---'
Copy-Item $dst $bak -Force
Write-Host ('Backup: ' + $bak)

Write-Host '--- 2/3 apply ---'
Copy-Item $src $dst -Force
Write-Host ('Applied: ' + $dst)

Write-Host '--- 3/3 verify ---'
$text = Get-Content $dst -Raw
$ins  = ([regex]::Matches($text, '- insert:')).Count
$sns  = [regex]::Matches($text, 'serverName:\s*(\S+)') | ForEach-Object { $_.Groups[1].Value }
Write-Host ('insert blocks : ' + $ins)
Write-Host ('serverName    : ' + ($sns -join ', '))
if ($ins -ge 1 -and ($sns -contains 'scipalhello') -and ($sns -contains 'scipal')) {
    Write-Host 'RESULT: OK' -ForegroundColor Green
} else {
    Write-Host 'RESULT: SUSPECT - expected both scipalhello and scipal' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Now start DSH Desktop and check the MCP settings page.'
Write-Host 'Expected tools: mcp__scipalhello__ping plus 5x mcp__scipal__*'
Write-Host 'If only the ping tool shows  -> SciPal side problem (script/Flask/timeout).'
Write-Host 'If none show                 -> DSH side / patch layer problem.'
