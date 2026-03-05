import asyncio
import os
import threading
import io
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
    return {"status": "Swarm Online (Low RAM Mode)", "monitor": "/live"}

@app.route('/live')
def live_video_feed():
    # 3 second delay to save CPU/RAM on screenshots
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
            <img src="/screenshot" alt="Waiting for browser..." />
            <p>Feed auto-refreshes every 3 seconds...</p>
        </body>
    </html>
    """

@app.route('/screenshot')
async def get_screenshot():
    global global_page
    if global_page and not global_page.is_closed():
        try:
            # Low quality screenshot to save bandwidth and memory
            img_bytes = await global_page.screenshot(type='jpeg', quality=30)
            return send_file(io.BytesIO(img_bytes), mimetype='image/jpeg')
        except:
            pass
    return "Not Ready", 404

async def swarm_engine():
    global global_page
    print("\n[START] 🚀 Kickstarting Engine (Light Mode)...", flush=True)
    
    while True:
        try:
            async with async_playwright() as p:
                print("[TASK 1] 🌐 Launching Headless Chromium...", flush=True)
                
                # MEMORY SAVING FLAGS FOR CLOUD
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox", 
                        "--disable-setuid-sandbox", 
                        "--disable-dev-shm-usage",
                        "--disable-gpu", 
                        "--single-process", 
                        "--no-zygote"
                    ]
                )
                
                context = await browser.new_context(storage_state="state.json")
                global_page = await context.new_page()
                
                print("[TASK 2] 📸 Navigating Instagram...", flush=True)
                await global_page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
                
                print("✅ [SUCCESS] Eyes on target! Go check /live", flush=True)
                
                while not global_page.is_closed():
                    await asyncio.sleep(60)
                    
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
