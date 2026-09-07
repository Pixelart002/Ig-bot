FROM python:3.13-slim

WORKDIR /app

# Node.js/npm are required by the Lightpanda browser runner.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies in a cacheable layer.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install the Lightpanda package in its own cacheable layer.
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

# Copy application/runtime files only after dependencies are installed.
COPY ig_bot.py browser_assist.py browser_assist_v2.py stats.py workflow.py run_logger.py otp_poller.py verification_bridge.py telegram_bot.py telegram_runner.py start_lightpanda.sh lightpanda_runner.js ./
RUN chmod +x start_lightpanda.sh

ENV VERIFICATION_HOST=0.0.0.0
ENV OTP_FILE=/app/otp.txt
ENV NPM_CONFIG_UPDATE_NOTIFIER=false

EXPOSE 8080

CMD ["./start_lightpanda.sh"]
