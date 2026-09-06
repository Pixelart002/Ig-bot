FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ig_bot.py browser_assist.py ./

# Default: AI identity/caption generator.
CMD ["python", "-u", "ig_bot.py"]
