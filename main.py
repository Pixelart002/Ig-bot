import os
import time
from flask import Flask, Response

app = Flask(__name__)
SCREENSHOT_PATH = "/tmp/stream.jpg"

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
    while True:
        try:
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    frame = f.read()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except Exception:
            pass
        time.sleep(0.2)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
