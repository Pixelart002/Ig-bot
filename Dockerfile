FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget curl libpango-1.0-0 libgb1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install Python packages & Playwright browsers
RUN pip install -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

EXPOSE 8000
CMD ["python", "main.py"]
