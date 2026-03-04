FROM python:3.10-slim

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    wget curl chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# 2. Setup Pinchtab (Using a more reliable link structure)
# Agar v0.0.3 fail ho raha hai, toh hum direct binary link ko verify karenge
RUN wget -q https://github.com/pinchtab/pinchtab/releases/latest/download/pinchtab_Linux_x86_64.tar.gz || \
    wget -q https://github.com/pinchtab/pinchtab/releases/download/v0.0.3/pinchtab_linux_amd64.tar.gz \
    && tar -xvf *.tar.gz \
    && find . -name "pinchtab" -exec mv {} /usr/local/bin/pinchtab \; \
    && chmod +x /usr/local/bin/pinchtab

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

EXPOSE 8000 8080

CMD ["sh", "-c", "pinchtab --port 8080 --headless & python main.py"]
