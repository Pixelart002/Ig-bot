#!/bin/bash

# 1. Start Virtual Display
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99
sleep 2

# 2. THE YOUTUBE ALGORITHM: FFmpeg HLS Streaming
# -b:v 500k = Max 500kbps data khayega (Ultra low data mode)
# -preset ultrafast = Server CPU ko crash hone se bachayega
mkdir -p /app/static/hls
ffmpeg -video_size 1280x720 -framerate 15 -f x11grab -i :99.0 \
       -c:v libx264 -preset ultrafast -tune zerolatency -b:v 500k \
       -f hls -hls_time 2 -hls_list_size 3 -hls_flags delete_segments \
       /app/static/hls/stream.m3u8 > /dev/null 2>&1 &

# 3. Start Auto-Bot in Background
(while true; do python3 bot.py; echo "Bot stopped, restarting..."; sleep 5; done) &

# 4. Start Web Server
exec gunicorn -b 0.0.0.0:8000 --workers 1 --threads 4 main:app
