FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir flask playwright playwright-stealth gunicorn

RUN playwright install chromium

EXPOSE 8000

# Gunicorn seedha start hoga, aur python script ke ANDAR xvfb chalega
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "main:app"]
