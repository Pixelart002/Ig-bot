#!/bin/bash

# 1. Start Virtual Display in 480p (RAM Saver!)
Xvfb :99 -screen 0 854x480x16 &
export DISPLAY=:99
sleep 2

# 2. Advanced HLS Encoding on Strict Diet
mkdir -p /app/static/hls
ffmpeg -video_size 854x480 -framerate 10 -f x11grab -i :99.0 \
       -c:v libx264 -preset ultrafast -tune zerolatency -b:v 150k \
       -threads 1 -f hls -hls_time 2 -hls_list_size 3 -hls_flags delete_segments \
       /app/static/hls/stream.m3u8 > /dev/null 2>&1 &

# 3. Background Bot Loop
(while true; do python3 bot.py; echo "Restarting bot..."; sleep 5; done) &

# 4. Gunicorn Server (Threads kam kar diye RAM bachane ke liye)
exec gunicorn -b 0.0.0.0:8000 --workers 1 --threads 2 main:app
