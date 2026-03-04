import asyncio
import os
import requests
import time
import threading
from flask import Flask
from playwright.async_api import async_playwright

# Universal Stealth Import Logic
try:
    from playwright_stealth import stealth_async as stealth_func
except ImportError:
    from playwright_stealth import stealth as stealth_func

app = Flask(__name__)

MISTRAL_URL = "https://mistral-ai-three.vercel.app/"
FLUX_URL = "https://flux-schnell.hello-kaiiddo.workers.dev/img"

@app.route('/')
def health():
    return {"status": "Aether-Swarm Active", "session": "Loaded"}

async def swarm_executor():
    while True:
        try:
            print("🧠 Brain (Mistral) is calculating...")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state="state.json")
                page = await context.new_page()
                
                # Apply stealth using the universal function
                await stealth_func(page)
                
                await page.goto("https://www.instagram.com/")
                await asyncio.sleep(5)
                
                if await page.query_selector('svg[aria-label="New Post"]'):
                    print("✅ Logged in successfully!")
                else:
                    print("❌ Session issue detected.")
                
                await browser.close()
                
            await asyncio.sleep(14400) # 4 hours sleep
            
        except Exception as e:
            print(f"⚠️ Swarm Error: {e}")
            await asyncio.sleep(300)

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(swarm_executor())
