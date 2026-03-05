FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

# Display aur Pip install
RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir flask playwright playwright-stealth gunicorn

RUN playwright install chromium

EXPOSE 8000

# Xvfb ke andar Gunicorn chalayenge taaki health check pass ho jaye
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x720x24", "gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "main:app"]
