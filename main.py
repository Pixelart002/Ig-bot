import asyncio
import os
import threading
import io
import time
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
    return {"status": "Aether-Swarm Online", "logs": "Check Koyeb Runtime Logs"}

@app.route('/live')
async def live_view():
    global global_page
    if global_page and not global_page.is_closed():
        img_bytes = await global_page.screenshot(type='jpeg', quality=60)
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
    return "⏳ Browser is warming up... Refresh in 10 seconds.", 202

async def swarm_engine():
    global global_page
    print("\n[START] 🚀 Initialize AI Swarm Engine...", flush=True)
    
    async with async_playwright() as p:
        print("[TASK 1] 🛠️  Installing/Checking Chromium...", flush=True)
        os.system("playwright install chromium")
        
        print("[TASK 2] 🌐 Launching Stealth Browser...", flush=True)
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        
        print("[TASK 3] 🔑 Loading state.json (Identity Injection)...", flush=True)
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth_func(global_page)
        
        print("[TASK 4] 📸 Navigating to Instagram Home...", flush=True)
        await global_page.goto("https://www.instagram.com/", wait_until="networkidle")
        
        while True:
            try:
                print(f"\n[HEARTBEAT] ❤️ Swarm Active at {time.ctime()}", flush=True)
                
                if await global_page.query_selector("svg[aria-label='New post']"):
                    print("✅ STATUS: Logged in successfully! Session is VALID.", flush=True)
                else:
                    print("⚠️ STATUS: Login not detected. Checking for popups...", flush=True)
                
                # Placeholder tasks for logging
                print("[TASK 5] 🧠 Brain (Mistral) analyzing 2026 trends...", flush=True)
                await asyncio.sleep(2)
                print("[TASK 6] 🎨 Artisan (Flux) preparing canvas...", flush=True)
                
                print("[SLEEP] 💤 Resting for 5 minutes...", flush=True)
                await asyncio.sleep(300) 
                
            except Exception as e:
                print(f"❌ ERROR in Swarm Loop: {str(e)}", flush=True)
                await asyncio.sleep(60)

if __name__ == "__main__":
    # Start the Bot in a background thread
    threading.Thread(target=lambda: asyncio.run(swarm_engine()), daemon=True).start()
    
    print("[SERVER] 📡 Flask Health-Check Server starting...", flush=True)
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
