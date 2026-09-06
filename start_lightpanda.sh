#!/usr/bin/env bash
set -euo pipefail

if [[ "${CDP_URL:-}" != ws://* && "${CDP_URL:-}" != wss://* ]]; then
  echo "ERROR: CDP_URL must be a Lightpanda Cloud WebSocket (ws:// or wss://)."
  exit 1
fi

echo "Using Lightpanda Cloud CDP"
exec python3 -u telegram_runner.py
