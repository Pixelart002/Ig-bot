FROM python:3.10-slim

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    wget curl chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 2. Setup Pinchtab (Foolproof Dynamic Link Fetching)
RUN LATEST_URL=$(curl -s https://api.github.com/repos/pinchtab/pinchtab/releases/latest | grep "browser_download_url.*linux_amd64.tar.gz" | cut -d '"' -f 4) \
    && wget -q $LATEST_URL -O pinchtab.tar.gz \
    && tar -xvf pinchtab.tar.gz \
    && find . -name "pinchtab" -type f -exec mv {} /usr/local/bin/pinchtab \; \
    && chmod +x /usr/local/bin/pinchtab

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

EXPOSE 8000 8080

CMD ["sh", "-c", "pinchtab --port 8080 --headless & python main.py"]
