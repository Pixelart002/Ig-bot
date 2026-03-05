FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app
COPY . /app

RUN apt-get update && apt-get install -y \
    python3-pip \
    xvfb \
    fluxbox \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir -r requirements.txt
RUN playwright install chromium

EXPOSE 8000
RUN chmod +x start.sh
CMD ["bash", "start.sh"]
