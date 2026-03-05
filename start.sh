#!/bin/bash
# Virtual Display on low RAM footprint
Xvfb :99 -screen 0 854x480x16 &
export DISPLAY=:99
sleep 2

# Auto-Restarting Bot
(while true; do python3 bot.py; echo "Restarting bot..."; sleep 5; done) &

# Foreground Web Server
exec gunicorn -b 0.0.0.0:8000 --workers 1 --threads 4 main:app
