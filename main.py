import asyncio
import os
import threading
import time
from flask import Flask, Response, render_template_string
from playwright.async_api import async_playwright

app = Flask(__name__)
# Global variable to store the latest frame
last_frame = None

@app.route('/')
def index():
    return """
    <html>
        <head>
            <title>🔴 Swarm Live OS</title>
            <style>
                body { background: #000; color: #0f0; font-family: 'Courier New', monospace; text-align: center; margin: 0; overflow: hidden; }
                .stream-container { width: 90vw; margin: 20px auto; border: 4px solid #333; border-radius: 8px; box-shadow: 0 0 30px rgba(0,255,0,0.2); position: relative; }
                .browser-ui { background: #333; height: 30px; border-top-left-radius: 4px; border-top-right-radius: 4px; display: flex; align-items: center; padding: 0 10px; }
                .dot { height: 10px; width: 10px; border-radius: 50%; margin-right: 5px; }
                img { width: 100%; display: block; }
                .status { position: absolute; top: 40px; right: 20px; background: rgba(0,0,0,0.7); padding: 5px 10px; border-radius: 4px; font-size: 12px; }
            </style>
        </head>
        <body>
            <h2>SWARM AGENT - LIVE INSTANCE</h2>
            <div class="stream-container">
                <div class="browser-ui">
                    <div class="dot" style="background: #ff5f56;"></div>
                    <div class="dot" style="background: #ffbd2e;"></div>
                    <div class="dot" style="background: #27c93f;"></div>
                    <span style="margin-left: 15px; color: #ccc; font-size: 12px;">Production Browser - Instagram.com</span>
                </div>
                <div class="status">● LIVE STREAMING</div>
                <img src="/video_feed">
            </div>
            <p>Direct Virtual Buffer Access | No-Lag Mode</p>
        </body>
    </html>
    """

def gen_frames():
    global last_frame
    while True:
        if last_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + last_frame + b'\r\n')
        time.sleep(0.1) # 10 Frames per second

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

async def browser_logic():
    global last_frame
    async with async_playwright() as p:
        # headless=False is compulsory for full UI
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--start-maximized"]
        )
        
        storage = "state.json" if os.path.exists("state.json") else None
        context = await browser.new_context(
            storage_state=storage,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = await context.new_page()
        await page.goto("https://www.instagram.com/", wait_until="networkidle")
        
        print("🚀 STREAM STARTED: Check /")

        while True:
            # Capturing the full browser window buffer
            last_frame = await page.screenshot(type='jpeg', quality=50)
            await asyncio.sleep(0.05) # Super fast capture

def run_browser():
    asyncio.run(browser_logic())

if __name__ == "__main__":
    # Start browser in a background thread
    threading.Thread(target=run_browser, daemon=True).start()
    # Start Flask
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, threaded=True)
