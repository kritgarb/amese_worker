#!/usr/bin/env bash
set -euo pipefail

DIR=${1:-completo/failed_events}

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
fi

exec python retry_failed.py --dir "$DIR"

