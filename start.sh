#!/bin/bash
# 1. Start Virtual Display
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99

# 2. Start Web Server in background
gunicorn -b 0.0.0.0:8000 --workers 1 --threads 4 main:app &

# 3. Start Browser Bot (Isse server free rahega)
python3 bot.py
