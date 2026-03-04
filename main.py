import asyncio
import os
import requests
import time
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from flask import Flask
import threading

app = Flask(__name__)

# --- AGENT ENDPOINTS ---
MISTRAL_URL = "https://mistral-ai-three.vercel.app/"
FLUX_URL = "https://flux-schnell.hello-kaiiddo.workers.dev/img"

@app.route('/')
def health():
    return {"status": "Aether-Swarm Active", "mode": "Production", "session": "Loaded"}

async def swarm_executor():
    while True:
        try:
            print("🧠 Sovereign (Mistral) is planning the next viral move...")
            # 1. Get Strategy from Mistral
            res = requests.get(MISTRAL_URL, params={"id": "Pixelart002", "question": "Generate a 2026 tech trend caption and a Flux image prompt."})
            logic = res.text
            
            print("🎨 Artisan (Flux) is painting the masterpiece...")
            # 2. Get Visuals from Flux
            img_res = requests.get(f"{FLUX_URL}?prompt=futuristic_ai_robot_2026_cinematic")
            with open("upload.jpg", "wb") as f:
                f.write(img_res.content)
            
            print("🚀 Executor (Playwright) is taking control...")
            # 3. Automation via Playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                # Injected state.json use kar rahe hain
                context = await browser.new_context(storage_state="state.json")
                page = await context.new_page()
                await stealth_async(page)
                
                await page.goto("https://www.instagram.com/")
                await asyncio.sleep(5)
                
                # Simple check if logged in
                if await page.query_selector('svg[aria-label="New Post"]'):
                    print("✅ Session Valid: Logged in as Pixelart002")
                    # Yahan Upload logic (Clicks) aayegi
                else:
                    print("❌ Session Expired: Please update cookies!")
                
                await browser.close()
                
            print("💤 Swarm resting for 4 hours...")
            await asyncio.sleep(14400) # 4 hours sleep
            
        except Exception as e:
            print(f"⚠️ Swarm Alert: {e}")
            await asyncio.sleep(300)

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(swarm_executor())
