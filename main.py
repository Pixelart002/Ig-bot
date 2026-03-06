import os, time, json
from flask import Flask, Response, request, render_template_string

app = Flask(__name__)
SCREENSHOT_PATH = "/tmp/stream.jpg"
LOG_PATH = "/tmp/swarm_logic.txt"
INST_PATH = "instructions.txt"

@app.route('/')
def index():
    logic_log = ""
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f: logic_log = f.read()
    
    inst_val = ""
    if os.path.exists(INST_PATH):
        with open(INST_PATH, 'r') as f: inst_val = f.read()

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 MANUS AGENT OS</title>
        <style>
            body { background: #0d0d0d; color: #e0e0e0; font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; }
            .sidebar { width: 300px; background: #151515; border-right: 1px solid #333; display: flex; flex-direction: column; padding: 15px; }
            .main-content { flex: 1; display: flex; flex-direction: column; padding: 15px; gap: 15px; }
            .preview-window { flex: 2; background: #000; border: 1px solid #444; border-radius: 8px; position: relative; overflow: hidden; }
            .preview-window img { width: 100%; height: 100%; object-fit: contain; }
            .terminal { flex: 1; background: #050505; border: 1px solid #00ff41; border-radius: 8px; padding: 10px; font-family: 'Courier New', monospace; font-size: 12px; color: #00ff41; overflow-y: auto; white-space: pre-wrap; }
            textarea { width: 100%; height: 80px; background: #222; color: #fff; border: 1px solid #444; border-radius: 5px; padding: 10px; }
            button { background: #00ff41; color: #000; border: none; padding: 10px; font-weight: bold; border-radius: 5px; cursor: pointer; margin-top: 10px; width: 100%; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h3>💬 Agent Chat</h3>
            <form onsubmit="sendGoal(event)">
                <textarea id="instBox" name="inst" placeholder="Enter Goal...">{{inst_val}}</textarea>
                <button type="submit">EXECUTE GOAL</button>
            </form>
        </div>
        <div class="main-content">
            <div class="preview-window"><img src="/video_feed"></div>
            <div class="terminal" id="terminal">{{logic_log}}</div>
        </div>
    </body>
    <script>
        // 🟢 JavaScript for Background Execution
        function sendGoal(event) {
            event.preventDefault(); // Rok diya page reload!
            const inst = document.getElementById('instBox').value;
            fetch('/update_inst', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: 'inst=' + encodeURIComponent(inst)
            }).then(() => {
                alert('Task Sent to Agent! ✅');
                document.getElementById('instBox').value = '';
            });
        }

        // Live Logs Fetcher
        setInterval(() => {
            fetch('/get_logs').then(r => r.text()).then(t => {
                const term = document.getElementById('terminal');
                term.innerText = t;
                term.scrollTop = term.scrollHeight; // Auto-scroll down
            });
        }, 2000);
    </script>
    </html>
    """, logic_log=logic_log, inst_val=inst_val)

@app.route('/update_inst', methods=['POST'])
def update_inst():
    with open(INST_PATH, 'w') as f: f.write(request.form.get('inst'))
    if os.path.exists(LOG_PATH): os.remove(LOG_PATH) # Purana kachra saaf
    return "OK", 200 # Redirect hataya, JSON response lagaya

@app.route('/get_logs')
def get_logs():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f: return f.read()
    return "Waiting for agent..."

def gen_frames():
    while True:
        try:
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f.read() + b'\r\n')
        except: pass
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)