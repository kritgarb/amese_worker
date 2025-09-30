#!/usr/bin/env bash
set -euo pipefail

# Ativa venv se existir
if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
fi

exec python monitor_bemsoft.py

