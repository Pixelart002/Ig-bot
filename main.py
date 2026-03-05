import asyncio
import os
import threading
import time
import subprocess
from flask import Flask, Response
from playwright.async_api import async_playwright

app = Flask(__name__)
last_frame = None

@app.route('/')
def index():
    return """
    <html>
        <head>
            <title>🔴 Swarm Live OS</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { background: #000; color: #0f0; font-family: 'Courier New', monospace; text-align: center; margin: 0; padding: 10px; }
                .stream-container { width: 100%; max-width: 1000px; margin: 0 auto; border: 2px solid #333; border-radius: 8px; position: relative; }
                .browser-ui { background: #222; height: 25px; border-top-left-radius: 6px; border-top-right-radius: 6px; display: flex; align-items: center; padding: 0 10px; }
                .dot { height: 10px; width: 10px; border-radius: 50%; margin-right: 6px; }
                img { width: 100%; display: block; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }
                .status { position: absolute; top: 35px; right: 10px; background: rgba(255,0,0,0.8); color: white; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; animation: blink 2s infinite; }
                @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
            </style>
        </head>
        <body>
            <h3>🧠 MANUS-AGENT: ACTIVE</h3>
            <div class="stream-container">
                <div class="browser-ui">
                    <div class="dot" style="background: #ff5f56;"></div>
                    <div class="dot" style="background: #ffbd2e;"></div>
                    <div class="dot" style="background: #27c93f;"></div>
                    <span style="margin-left: 10px; color: #aaa; font-size: 12px;">Virtual Display :99 - Instagram</span>
                </div>
                <div class="status">● LIVE</div>
                <img src="/video_feed" alt="Booting OS environment...">
            </div>
        </body>
    </html>
    """

def gen_frames():
    global last_frame
    while True:
        if last_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + last_frame + b'\r\n')
        time.sleep(0.2)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

async def browser_logic():
    global last_frame
    print("\n[START] 🚀 Booting Virtual Desktop internally...", flush=True)
    
    # Python script ke andar Xvfb start kar rahe hain taaki Gunicorn block na ho
    os.environ["DISPLAY"] = ":99"
    subprocess.Popen(["Xvfb", ":99", "-screen", "0", "1280x720x24"])
    
    # Wait for Xvfb to start
    await asyncio.sleep(2)
    
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--start-maximized"]
                )
                
                storage = "state.json" if os.path.exists("state.json") else None
                context = await browser.new_context(
                    storage_state=storage,
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()
                
                print("[TASK] 🌐 Navigating to Target...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                
                scroll_dir = 1
                while not page.is_closed():
                    last_frame = await page.screenshot(type='jpeg', quality=30)
                    await page.evaluate(f"window.scrollBy(0, {20 * scroll_dir})")
                    await asyncio.sleep(0.2)
        except Exception as e:
            print(f"🛑 [RESTARTING] {str(e)}", flush=True)
            await asyncio.sleep(5)

def run_browser():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(browser_logic())

threading.Thread(target=run_browser, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
