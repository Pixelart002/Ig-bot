#!/usr/bin/env bash
set -euo pipefail

# Lightpanda must stay private/local; the FastAPI bridge is the only public browser surface.
npm run browser > /tmp/lightpanda.log 2>&1 &
BROWSER_PID=$!

cleanup() {
  kill "$BROWSER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
  if python3 - <<'PY'
import requests
try:
    r = requests.get('http://127.0.0.1:9222/json/version', timeout=1)
    r.raise_for_status()
except Exception:
    raise SystemExit(1)
PY
  then
    break
  fi
  if ! kill -0 "$BROWSER_PID" 2>/dev/null; then
    cat /tmp/lightpanda.log
    exit 1
  fi
  sleep 1
done

python3 - <<'PY'
import requests
r = requests.get('http://127.0.0.1:9222/json/version', timeout=2)
r.raise_for_status()
print('Lightpanda CDP is ready:', r.json().get('Browser', 'unknown'))
PY

exec python3 -u telegram_bot.py
