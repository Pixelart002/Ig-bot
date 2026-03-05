import os
from flask import Flask, send_from_directory

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
        <head>
            <title>🔴 Swarm Ultra-Smooth Stream</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
            <style>
                body { background: #000; color: #0f0; font-family: 'Courier New', monospace; text-align: center; margin: 0; padding: 10px; }
                .stream-container { width: 100%; max-width: 854px; margin: 0 auto; border: 2px solid #333; border-radius: 8px; position: relative; }
                video { width: 100%; display: block; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px; }
                .browser-ui { background: #222; height: 25px; border-top-left-radius: 6px; border-top-right-radius: 6px; display: flex; align-items: center; padding: 0 10px; }
                .dot { height: 10px; width: 10px; border-radius: 50%; margin-right: 6px; }
                .status { position: absolute; top: 35px; right: 10px; background: rgba(255,0,0,0.8); color: white; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; animation: blink 2s infinite; z-index: 10; }
                @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
            </style>
        </head>
        <body>
            <h3>🧠 MANUS-AGENT: HLS STREAM (480p)</h3>
            <div class="stream-container">
                <div class="browser-ui">
                    <div class="dot" style="background: #ff5f56;"></div>
                    <div class="dot" style="background: #ffbd2e;"></div>
                    <div class="dot" style="background: #27c93f;"></div>
                    <span style="margin-left: 10px; color: #aaa; font-size: 12px;">Low-RAM HLS Feed</span>
                </div>
                <div class="status">● LIVE</div>
                <video id="video" autoplay muted controls></video>
            </div>
            
            <script>
                var video = document.getElementById('video');
                var videoSrc = '/hls/stream.m3u8';
                
                if (Hls.isSupported()) {
                    var hls = new Hls({ liveSyncDurationCount: 2, liveMaxLatencyDurationCount: 3 });
                    hls.loadSource(videoSrc);
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, function() { video.play(); });
                } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
                    video.src = videoSrc;
                    video.addEventListener('loadedmetadata', function() { video.play(); });
                }
            </script>
        </body>
    </html>
    """

@app.route('/hls/<path:filename>')
def hls_serve(filename):
    return send_from_directory('/app/static/hls', filename)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)
