FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir flask playwright playwright-stealth gunicorn

RUN playwright install chromium

EXPOSE 8000

# Hum command ki jagah script use karenge
RUN chmod +x start.sh
CMD ["./start.sh"]
