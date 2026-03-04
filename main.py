import asyncio
import os
import threading
import io
from flask import Flask, send_file
from playwright.async_api import async_playwright
from playwright_stealth import stealth

app = Flask(__name__)
global_page = None 

@app.route('/')
def health():
    return {"status": "Aether-Swarm Online", "monitor": "/live"}

@app.route('/live')
async def live_view():
    global global_page
    try:
        if global_page and not global_page.is_closed():
            img_bytes = await global_page.screenshot(type='jpeg', quality=60)
            return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
        return "⏳ Browser is warming up... Refresh in 10 seconds.", 202
    except Exception as e:
        return f"⚠️ Live View Error: {str(e)}", 500

async def swarm_engine():
    global global_page
    async with async_playwright() as p:
        print("🚀 Starting Production Browser...")
        # Playwright ko install karna pad sakta hai agar build mein nahi hua
        os.system("playwright install chromium")
        
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth(global_page)
        
        await global_page.goto("https://www.instagram.com/")
        print("✅ Live Stream Ready!")
        
        while True:
            await asyncio.sleep(60) # Keep-alive loop

if __name__ == "__main__":
    threading.Thread(target=lambda: asyncio.run(swarm_engine()), daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
