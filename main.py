import asyncio
import os
import threading
import io
from flask import Flask, send_file
from playwright.async_api import async_playwright

app = Flask(__name__)
global_page = None 

@app.route('/')
def health():
    return {"status": "Aether-Swarm Running", "check": "/live"}

@app.route('/live')
async def live_view():
    global global_page
    if global_page and not global_page.is_closed():
        img_bytes = await global_page.screenshot(type='jpeg', quality=60)
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
    return "⏳ Browser is still missing libraries or launching...", 202

async def swarm_engine():
    global global_page
    print("\n[START] 🚀 Kickstarting Engine...", flush=True)
    
    while True:
        try:
            async with async_playwright() as p:
                print("[TASK 1] 🛠️ Ensuring Binaries...", flush=True)
                os.system("playwright install chromium")
                
                print("[TASK 2] 🌐 Launching Chromium...", flush=True)
                # Added 'disable-setuid-sandbox' for cloud environments
                browser = await p.chromium.launch(
                    headless=True, 
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(storage_state="state.json")
                global_page = await context.new_page()
                
                print("[TASK 3] 📸 Navigating Instagram...", flush=True)
                await global_page.goto("https://www.instagram.com/", wait_until="networkidle")
                print("✅ [SUCCESS] Swarm is eyes-on-target!", flush=True)
                
                while not global_page.is_closed():
                    await asyncio.sleep(60)
                    
        except Exception as e:
            print(f"🛑 [CRASH] Details: {str(e)}", flush=True)
            print("🔄 [RETRY] Restarting in 15 seconds...", flush=True)
            await asyncio.sleep(15)

def start_swarm():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(swarm_engine())

threading.Thread(target=start_swarm, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
