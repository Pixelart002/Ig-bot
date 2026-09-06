FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy every runtime module used by the Telegram/Lightpanda Cloud workflow.
COPY ig_bot.py browser_assist.py stats.py workflow.py run_logger.py otp_poller.py verification_bridge.py telegram_bot.py telegram_runner.py start_lightpanda.sh ./
RUN chmod +x start_lightpanda.sh

ENV VERIFICATION_HOST=0.0.0.0
ENV OTP_FILE=/app/otp.txt

EXPOSE 8080

CMD ["./start_lightpanda.sh"]
