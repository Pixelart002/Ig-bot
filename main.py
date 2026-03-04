import asyncio
import os
import requests
import time
from playwright.async_api import async_playwright
from playwright_stealth import stealth  # Changed this line
from flask import Flask
import threading

app = Flask(__name__)

MISTRAL_URL = "https://mistral-ai-three.vercel.app/"
FLUX_URL = "https://flux-schnell.hello-kaiiddo.workers.dev/img"

@app.route('/')
def health():
    return {"status": "Aether-Swarm Active", "mode": "Production", "session": "Loaded"}

async def swarm_executor():
    while True:
        try:
            print("🧠 Sovereign (Mistral) is planning...")
            # Step 1: Logic
            # (Keeping it simple for the fix)
            
            print("🚀 Executor (Playwright) starting...")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(storage_state="state.json")
                page = await context.new_page()
                
                # Use 'stealth' instead of 'stealth_async'
                await stealth(page) 
                
                await page.goto("https://www.instagram.com/")
                await asyncio.sleep(5)
                
                if await page.query_selector('svg[aria-label="New Post"]'):
                    print("✅ Session Valid: Logged in!")
                else:
                    print("❌ Session Expired!")
                
                await browser.close()
                
            await asyncio.sleep(14400)
            
        except Exception as e:
            print(f"⚠️ Swarm Alert: {e}")
            await asyncio.sleep(300)

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(swarm_executor())
