#!/bin/bash

# 1. Start Display
Xvfb :99 -screen 0 854x480x16 &
export DISPLAY=:99

# 2. Delay the Bot (Isse Koyeb ka 5s health check pass ho jayega)
(sleep 4 && while true; do python3 bot.py; echo "Bot stopped, restarting..."; sleep 5; done) &

# 3. Start Web Server IMMEDIATELY in foreground
exec gunicorn -b 0.0.0.0:8000 --workers 1 --threads 2 main:app
