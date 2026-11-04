#!/bin/sh
set -eu

MODE="${APP_MODE:-DEV_MODE}"
PORT="${PORT:-5000}"

case "$MODE" in
  DEV_MODE|dev)
    echo "SciPal mode: DEV_MODE (Flask development server)"
    exec python api_server.py
    ;;
  PROD_MODE|prod)
    echo "SciPal mode: PROD_MODE (gunicorn)"
    exec gunicorn \
      --bind "0.0.0.0:${PORT}" \
      --workers "${GUNICORN_WORKERS:-1}" \
      --threads "${GUNICORN_THREADS:-4}" \
      --timeout "${GUNICORN_TIMEOUT:-300}" \
      --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
      --access-logfile - \
      --error-logfile - \
      api_server:app
    ;;
  *)
    echo "Invalid APP_MODE='$MODE'; use DEV_MODE or PROD_MODE" >&2
    exit 2
    ;;
esac
