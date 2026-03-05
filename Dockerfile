FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--worker-class", "gthread", "main:app"]
