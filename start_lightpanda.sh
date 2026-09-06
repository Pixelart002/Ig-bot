#!/usr/bin/env bash
set -euo pipefail

npm install
exec npm run browser
