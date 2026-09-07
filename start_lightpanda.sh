#!/usr/bin/env bash
set -euo pipefail

# Allow a local, gitignored .env file for development while leaving deployed
# environments to provide their variables through the platform's secret store.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "${CDP_URL:-}" != ws://* && "${CDP_URL:-}" != wss://* ]]; then
  echo "ERROR: CDP_URL must be a Lightpanda Cloud WebSocket (ws:// or wss://)."
  exit 1
fi

echo "Using Lightpanda Cloud CDP"
exec python3 -u telegram_runner.py
