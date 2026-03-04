FROM python:3.10-slim
RUN apt-get update && apt-get install -y wget curl chromium chromium-driver && rm -rf /var/lib/apt/lists/*
RUN wget https://github.com/pinchtab/pinchtab/releases/download/v0.0.3/pinchtab_Linux_x86_64.tar.gz \
    && tar -xvf pinchtab_Linux_x86_64.tar.gz && mv pinchtab /usr/local/bin/ && chmod +x /usr/local/bin/pinchtab
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8000 8080
CMD ["sh", "-c", "pinchtab --port 8080 --headless & python main.py"]
