#!/usr/bin/env bash
set -euo pipefail

# Ativa venv se existir
if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python "${SCRIPT_DIR}/../main.py"
