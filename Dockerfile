FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

# FFmpeg install kar rahe hain for YouTube-style HLS streaming
RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    fluxbox \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir -r requirements.txt
RUN playwright install chromium

RUN mkdir -p /app/static/hls
EXPOSE 8000

CMD ["bash", "start.sh"]
