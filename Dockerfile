FROM node:22-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund \
    && npx @lightpanda/browser install latest

COPY ig_bot.py browser_assist.py stats.py workflow.py verification_bridge.py telegram_bot.py start_lightpanda.sh lightpanda_runner.js ./
RUN chmod +x start_lightpanda.sh

ENV CDP_HOST=127.0.0.1
ENV CDP_PORT=9222
ENV CDP_URL=http://127.0.0.1:9222
ENV VERIFICATION_HOST=0.0.0.0

EXPOSE 8080

CMD ["./start_lightpanda.sh"]
