import asyncio
import os
import threading
from flask import Flask, send_file
from playwright.async_api import async_playwright

try:
    from playwright_stealth import stealth_async as stealth_func
except ImportError:
    from playwright_stealth import stealth as stealth_func

app = Flask(__name__)
# Yahan photo save hogi
SCREENSHOT_PATH = "/workspace/latest_screenshot.jpg"

@app.route('/')
def health():
    # Ye page turant khulega
    return {"status": "Swarm Online - Deadlock Fixed!", "monitor": "/live"}

@app.route('/live')
def live_video_feed():
    return """
    <html>
        <head>
            <meta http-equiv="refresh" content="3">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>🔴 Live Swarm Feed</title>
            <style>
                body { background: #111; color: #0f0; font-family: monospace; text-align: center; margin: 0; padding: 20px; }
                img { max-width: 100%; border: 3px solid #0f0; border-radius: 10px; margin-top: 15px; }
            </style>
        </head>
        <body>
            <div>🔴 LIVE: Instagram Bot Monitor</div>
            <img src="/screenshot" alt="Waiting for bot to click a picture..." />
            <p>Feed auto-refreshes every 3 seconds...</p>
        </body>
    </html>
    """

@app.route('/screenshot')
def get_screenshot():
    # Flask sirf hard-disk se photo padhega, bot se baat nahi karega
    if os.path.exists(SCREENSHOT_PATH):
        return send_file(SCREENSHOT_PATH, mimetype='image/jpeg')
    return "Not Ready", 404

async def swarm_engine():
    print("\n[START] 🚀 Bot Engine Started...", flush=True)
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"]
                )
                
                # Check if state.json exists
                storage = "state.json" if os.path.exists("state.json") else None
                context = await browser.new_context(storage_state=storage)
                page = await context.new_page()
                
                print("[TASK 2] 📸 Navigating Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
                print("✅ [SUCCESS] Eyes on target! Broadcasting to /live", flush=True)
                
                # Bot har 3 second mein photo kheench kar folder mein daalega
                while not page.is_closed():
                    await page.screenshot(path=SCREENSHOT_PATH, type='jpeg', quality=30)
                    await asyncio.sleep(3)
                    
        except Exception as e:
            print(f"🛑 [CRASH] Details: {str(e)}", flush=True)
            await asyncio.sleep(15)

def start_swarm():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(swarm_engine())

threading.Thread(target=start_swarm, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)
