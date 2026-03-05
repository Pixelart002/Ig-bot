FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Worker=1 to save RAM, Threads=2 to handle multiple web requests
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "main:app"]
