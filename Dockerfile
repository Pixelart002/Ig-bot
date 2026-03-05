# Microsoft ki official Playwright image (Saari libraries isme inbuilt hain!)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Folder set karo
WORKDIR /workspace

# Python packages install karo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Apna code copy karo (main.py, state.json etc.)
COPY . .

# Port batao
EXPOSE 8000

# Server start karo
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "2", "main:app"]
