FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ig_bot.py .

CMD ["python", "-u", "ig_bot.py"]