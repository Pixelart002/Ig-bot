import asyncio
import os
import threading
from flask import Flask, send_file
from playwright.async_api import async_playwright
from playwright_stealth import stealth
import io

app = Flask(__name__)
global_page = None  # Isme live browser screen save hogi

@app.route('/')
def health():
    return {"status": "Aether-Swarm Active", "live_view": "/live"}

@app.route('/live')
async def live_view():
    global global_page
    if global_page:
        # Live screenshot lekar browser mein dikhana
        img_bytes = await global_page.screenshot(type='jpeg', quality=50)
        return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
    return "⚠️ Browser abhi band hai ya load ho raha hai. Thoda wait karein."

async def swarm_executor():
    global global_page
    async with async_playwright() as p:
        print("🚀 Launching Live Browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state="state.json")
        global_page = await context.new_page()
        await stealth(global_page)
        
        while True:
            try:
                print("📸 Monitoring Instagram...")
                await global_page.goto("https://www.instagram.com/")
                await asyncio.sleep(60) # Har 1 min mein refresh (testing ke liye)
            except Exception as e:
                print(f"⚠️ Error: {e}")
                await asyncio.sleep(10)

def run_flask():
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(swarm_executor())
