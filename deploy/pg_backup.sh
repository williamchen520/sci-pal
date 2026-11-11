#!/usr/bin/env bash
# Version-matched PostgreSQL backups: core every 6h, corpus every 7d.
set -u

OUT="${SCIPAL_PG_BACKUP_DIR:-/app/backups/pg}"
CORE_DSN="${SCIPAL_CORE_DSN:-}"
CORPUS_DSN="${SCIPAL_PG_CORPUS_DSN:-}"
INTERVAL="${SCIPAL_PG_BACKUP_INTERVAL_SECONDS:-3600}"
CORE_INTERVAL="${SCIPAL_PG_BACKUP_CORE_SECONDS:-21600}"
CORPUS_INTERVAL="${SCIPAL_PG_BACKUP_CORPUS_SECONDS:-604800}"
CORE_RETENTION="${SCIPAL_PG_BACKUP_CORE_RETENTION_SECONDS:-604800}"
CORPUS_RETENTION="${SCIPAL_PG_BACKUP_CORPUS_RETENTION_SECONDS:-2419200}"

mkdir -p "$OUT"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

last_age() {
  local name="$1" latest
  latest=$(find "$OUT" -maxdepth 1 -name "${name}-*.dump" -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
  if [ -z "$latest" ]; then echo 999999999; return; fi
  echo $(( $(date +%s) - ${latest%.*} ))
}

dump() {
  local name="$1" dsn="$2"
  if [ -z "$dsn" ]; then log "skip $name: DSN missing"; return 1; fi
  local target="$OUT/${name}-$(date -u +%Y%m%d-%H%M%S).dump"
  log "start $name -> $target"
  if pg_dump "$dsn" --format=custom --no-owner --no-acl --file "$target" \
     && pg_restore --list "$target" >/dev/null 2>&1; then
    log "ok $name $(du -h "$target" | cut -f1)"
  else
    log "FAILED $name; removing partial"
    rm -f "$target"
    return 1
  fi
}

prune() {
  local name="$1" retention="$2"
  find "$OUT" -maxdepth 1 -name "${name}-*.dump" -mtime +$(( retention / 86400 )) -print -delete 2>/dev/null
}

trap 'log "stopping"; exit 0' TERM INT
while true; do
  if [ "$(last_age core)" -ge "$CORE_INTERVAL" ]; then
    dump core "$CORE_DSN" || true
    prune core "$CORE_RETENTION"
  fi
  if [ "$(last_age corpus)" -ge "$CORPUS_INTERVAL" ]; then
    dump corpus "$CORPUS_DSN" || true
    prune corpus "$CORPUS_RETENTION"
  fi
  sleep "$INTERVAL"
done
