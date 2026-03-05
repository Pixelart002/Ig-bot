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
    return {"status": "FORCED ON 8080", "monitor": "/live"}

@app.route('/live')
async def live_view():
    global global_page
    if global_page:
        img_bytes = await global_page.screenshot(type='jpeg', quality=50)
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
    return "Warming up...", 202

async def swarm_engine():
    global global_page
    async with async_playwright() as p:
        os.system("playwright install chromium")
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth_func(global_page)
        await global_page.goto("https://www.instagram.com/")
        print("✅ [PORT 8080] Browser is LIVE!", flush=True)
        while True: await asyncio.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=lambda: asyncio.run(swarm_engine()), daemon=True).start()
    # Yahan humne environment variable ko dhokha de diya
    app.run(host='0.0.0.0', port=8080) 
