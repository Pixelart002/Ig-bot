import asyncio
import os
import threading
import io
import time
from flask import Flask, send_file
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async as stealth_func
except ImportError:
    from playwright_stealth import stealth as stealth_func

app = Flask(__name__)
global_page = None 

@app.route('/')
def health():
    return {"status": "Dual-Port Active", "ports": [8000, 8080], "engine": "Check /live"}

@app.route('/live')
async def live_view():
    global global_page
    try:
        if global_page and not global_page.is_closed():
            img_bytes = await global_page.screenshot(type='jpeg', quality=60)
            return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
        return "⏳ Waiting for Browser to stabilize... Refresh in 30s.", 202
    except Exception as e:
        return f"⚠️ Live View Error: {str(e)}", 500

async def swarm_engine():
    global global_page
    print("\n[START] 🚀 Initializing Background Engine...", flush=True)
    
    while True: # Auto-restart loop if browser crashes
        try:
            async with async_playwright() as p:
                print("[TASK 1] 🛠️  Installing Browser Binaries...", flush=True)
                os.system("playwright install chromium")
                
                print("[TASK 2] 🌐 Launching Chromium Shell...", flush=True)
                # Added --disable-gpu for extra stability in cloud
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
                
                context = await browser.new_context(storage_state="state.json")
                global_page = await context.new_page()
                await stealth_func(global_page)
                
                print("[TASK 3] 📸 Loading Instagram...", flush=True)
                await global_page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                print("✅ [ENGINE] Success! Instagram is live.", flush=True)
                
                while True:
                    if global_page.is_closed(): break
                    await asyncio.sleep(60)
        except Exception as e:
            print(f"🛑 [CRASH] Browser failed: {str(e)}", flush=True)
            print("🔄 [RETRY] Restarting engine in 10 seconds...", flush=True)
            await asyncio.sleep(10)

def start_swarm():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(swarm_engine())

threading.Thread(target=start_swarm, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
