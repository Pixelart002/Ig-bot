import os
import asyncio
import threading
from flask import Flask
import subprocess

app = Flask(__name__)

@app.route('/')
def health():
    return {"status": "Aether-Swarm is Running via Buildpack", "agents": "Active"}

def install_playwright():
    print("📦 Installing Playwright Browsers...")
    subprocess.run(["playwright", "install", "chromium"])

def swarm_logic():
    # Playwright install hone ka intezar karein
    install_playwright()
    while True:
        print("🧠 Swarm Agents are analyzing trends...")
        # Tumhari Mistral + Flux + Playwright logic yahan aayegi
        import time
        time.sleep(3600)

if __name__ == "__main__":
    # Swarm ko alag thread mein chalayein
    threading.Thread(target=swarm_logic, daemon=True).start()
    # Flask for Koyeb Health Check
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
