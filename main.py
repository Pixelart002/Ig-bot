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
    return {"status": "SWARM ACTIVE", "port": "8080", "monitor": "/live"}

@app.route('/live')
async def live_view():
    global global_page
    try:
        if global_page and not global_page.is_closed():
            img_bytes = await global_page.screenshot(type='jpeg', quality=60)
            return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
        return "⏳ Engine is starting on Port 8080...", 202
    except Exception as e:
        return f"⚠️ Error: {str(e)}", 500

async def swarm_engine():
    global global_page
    async with async_playwright() as p:
        print("[DEBUG] 🛠️ Launching on New Port Strategy...", flush=True)
        os.system("playwright install chromium")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth_func(global_page)
        await global_page.goto("https://www.instagram.com/")
        print("✅ [PORT 8080] Instagram Ready!", flush=True)
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=lambda: asyncio.run(swarm_engine()), daemon=True).start()
    # Port badal kar 8080 kar diya hai
    port = int(os.environ.get("PORT", 8080))
    print(f"[SERVER] 📡 Starting on Port: {port}", flush=True)
    app.run(host='0.0.0.0', port=port, debug=False)
