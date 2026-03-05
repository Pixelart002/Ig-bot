FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

# Display aur Streaming tools install kar rahe hain
RUN apt-get update && apt-get install -y \
    xvfb \
    fluxbox \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir flask flask[async] playwright playwright-stealth gunicorn

# Browser install
RUN playwright install chromium

# Xvfb Virtual Screen size set kar rahe hain (1280x720)
CMD ["xvfb-run", "--server-args=-screen 0 1280x720x24", "python", "main.py"]
