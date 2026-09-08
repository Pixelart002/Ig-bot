FROM node:22-bookworm-slim

WORKDIR /app

# Python runtime for the FastAPI/Telegram control plane.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies in a cacheable layer.
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Install Node dependencies in a cacheable layer.
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

# Copy application/runtime files that exist in the repository.
COPY ig_bot.py browser_assist.py browser_assist_v2.py stats.py workflow.py run_logger.py otp_poller.py verification_bridge.py telegram_bot.py telegram_runner.py start_lightpanda.sh lightpanda_runner.js ./
RUN chmod +x start_lightpanda.sh

ENV VERIFICATION_HOST=0.0.0.0
ENV OTP_FILE=/app/otp.txt
ENV NPM_CONFIG_UPDATE_NOTIFIER=false

EXPOSE 8080

CMD ["./start_lightpanda.sh"]
