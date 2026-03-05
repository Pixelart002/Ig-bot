# Update to latest Playwright image to match python package version
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Using gthread worker to be more efficient with low RAM
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--worker-class", "gthread", "main:app"]
