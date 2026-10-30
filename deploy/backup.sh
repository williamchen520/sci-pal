#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python deploy/backup.py --data data --out backups
