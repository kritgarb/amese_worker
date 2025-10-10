#!/usr/bin/env bash
set -euo pipefail

# Encerra processos do monitor pelo nome do script
pkill -f "main.py" || true
