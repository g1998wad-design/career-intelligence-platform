#!/bin/zsh
set -eu
BASE_DIR=/Users/gurkiratsingh/JS_BASICS
cd "$BASE_DIR"

if [[ -f "$BASE_DIR/.env" ]]; then
  set -a
  source "$BASE_DIR/.env"
  set +a
fi

case "${1:-}" in
  review)
    exec "$BASE_DIR/.venv/bin/uvicorn" review_app:app --host 127.0.0.1 --port 8765
    ;;
  selected-worker)
    exec "$BASE_DIR/.venv/bin/python3" -u prepare_selected_jobs.py --poll-seconds 15
    ;;
  application-worker)
    exec "$BASE_DIR/.venv/bin/python3" -u application_worker.py
    ;;
  *)
    echo "Usage: $0 review|selected-worker|application-worker" >&2
    exit 2
    ;;
esac
