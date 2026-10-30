$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python deploy/backup.py --data data --out backups
