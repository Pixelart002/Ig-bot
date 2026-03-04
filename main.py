import asyncio
import os
import threading
import io
import time
import sys
from flask import Flask, send_file
from playwright.async_api import async_playwright

# Universal Stealth Import
try:
    from playwright_stealth import stealth_async as stealth_func
except ImportError:
    from playwright_stealth import stealth as stealth_func

app = Flask(__name__)
global_page = None 

@app.route('/')
def health():
    return {"status": "DEBUG MODE ACTIVE", "global_page": str(global_page)}

@app.route('/live')
async def live_view():
    global global_page
    try:
        if global_page and not global_page.is_closed():
            img_bytes = await global_page.screenshot(type='jpeg', quality=70)
            return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
        return "🛠️ [DEBUG] Browser not initialized yet. Check logs for Task 2.", 202
    except Exception as e:
        return f"❌ [DEBUG ERROR] {str(e)}", 500

async def swarm_engine():
    global global_page
    print("\n[DEBUG START] 🚀 Starting Swarm Engine...", flush=True)
    
    async with async_playwright() as p:
        print("[TASK 1] 🛠️ Verifying Chromium installation...", flush=True)
        # Check if browser exists to avoid redundant installs
        os.system("playwright install chromium")
        
        print("[TASK 2] 🌐 Launching Browser (Headless Mode)...", flush=True)
        try:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
            context = await browser.new_context(storage_state="state.json")
            global_page = await context.new_page()
            await stealth_func(global_page)
            
            print("[TASK 3] 📸 Loading Instagram...", flush=True)
            await global_page.goto("https://www.instagram.com/", wait_until="networkidle")
            print("✅ [DEBUG] Instagram Loaded Successfully!", flush=True)
            
            while True:
                # Periodic status check
                title = await global_page.title()
                print(f"[HEARTBEAT] 💓 On Page: {title}", flush=True)
                await asyncio.sleep(60)
                
        except Exception as e:
            print(f"🛑 [FATAL BROWSER ERROR] {str(e)}", flush=True)

if __name__ == "__main__":
    # Run engine in background
    threading.Thread(target=lambda: asyncio.run(swarm_engine()), daemon=True).start()
    
    print("[SERVER] 📡 Flask Debug Server starting on Port 8000...", flush=True)
    port = int(os.environ.get("PORT", 8000))
    # Debug mode ON
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)
