FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ig_bot.py browser_assist.py stats.py workflow.py verification_bridge.py telegram_bot.py ./

# Telegram control plane + HTTPS verification bridge. Lightpanda/CDP runs separately.
CMD ["python", "-u", "telegram_bot.py"]
