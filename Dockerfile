FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ig_bot.py browser_assist.py stats.py telegram_bot.py ./

# Telegram control plane. Lightpanda/CDP runs as a separate browser process/service.
CMD ["python", "-u", "telegram_bot.py"]
