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
    return {"status": "Aether-Swarm Dual-Port Active", "ports": [8000, 8080]}

@app.route('/live')
async def live_view():
    global global_page
    if global_page and not global_page.is_closed():
        img_bytes = await global_page.screenshot(type='jpeg', quality=60)
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
    return "⏳ Swarm Engine is warming up... Check logs for Task 2.", 202

async def swarm_engine():
    global global_page
    print("\n[START] 🚀 Initializing Background Engine...", flush=True)
    async with async_playwright() as p:
        os.system("playwright install chromium")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth_func(global_page)
        await global_page.goto("https://www.instagram.com/")
        print("✅ [ENGINE] Instagram successfully loaded in background!", flush=True)
        while True:
            await asyncio.sleep(60)

# Gunicorn ke liye thread yahan start karna zaruri hai
def start_swarm():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(swarm_engine())

# App start hote hi thread chala do
threading.Thread(target=start_swarm, daemon=True).start()

if __name__ == "__main__":
    # Manual run ke liye default port
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
