import os, time
from flask import Flask, Response, request, render_template_string

app = Flask(__name__)
SCREENSHOT_PATH = "/tmp/stream.jpg"
LOG_PATH = "/tmp/swarm_logic.txt"
TODO_PATH = "/tmp/todo.json"
INST_PATH = "instructions.txt"

@app.route('/')
def index():
    logic_log = ""
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f: logic_log = f.read()
    
    tasks = []
    if os.path.exists(TODO_PATH):
        with open(TODO_PATH, 'r') as f: 
            try: tasks = json.load(f)
            except: pass

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 MANUS AGENT OS</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { background: #0d0d0d; color: #e0e0e0; font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; }
            .sidebar { width: 300px; background: #151515; border-right: 1px solid #333; display: flex; flex-direction: column; padding: 15px; }
            .main-content { flex: 1; display: flex; flex-direction: column; padding: 15px; gap: 15px; }
            .right-panel { width: 250px; background: #151515; border-left: 1px solid #333; padding: 15px; }
            
            .preview-window { flex: 2; background: #000; border: 1px solid #444; border-radius: 8px; position: relative; overflow: hidden; }
            .preview-window img { width: 100%; height: 100%; object-fit: contain; }
            
            .terminal { flex: 1; background: #050505; border: 1px solid #00ff41; border-radius: 8px; padding: 10px; font-family: 'Courier New', monospace; font-size: 12px; color: #00ff41; overflow-y: auto; white-space: pre-wrap; }
            
            h3 { font-size: 14px; margin-top: 0; color: #888; text-transform: uppercase; letter-spacing: 1px; }
            .task-item { background: #222; padding: 8px; border-radius: 4px; margin-bottom: 5px; font-size: 12px; border-left: 3px solid #0f0; }
            
            textarea { width: 100%; height: 80px; background: #222; color: #fff; border: 1px solid #444; border-radius: 5px; padding: 10px; resize: none; }
            button { background: #00ff41; color: #000; border: none; padding: 10px; font-weight: bold; border-radius: 5px; cursor: pointer; margin-top: 10px; }
            .status-tag { position: absolute; top: 10px; right: 10px; background: rgba(255,0,0,0.7); padding: 2px 8px; border-radius: 4px; font-size: 10px; color: white; animation: blink 1s infinite; }
            @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h3>💬 Chat & Input</h3>
            <form action="/update_inst" method="POST">
                <textarea name="inst" placeholder="Enter Goal (e.g. Go to Google and search for latest AI news)">{{inst}}</textarea>
                <button type="submit">EXECUTE GOAL</button>
            </form>
            <div style="margin-top: 20px;">
                <h3>📜 Chat Menu</h3>
                <div style="font-size: 12px; color: #666;">- Autonomous Mode: ON<br>- Browser: Playwright<br>- Brain: Qwen-2.5 7B</div>
            </div>
        </div>

        <div class="main-content">
            <div class="preview-window">
                <div class="status-tag">LIVE AGENT</div>
                <img src="/video_feed">
            </div>
            <div class="terminal" id="terminal">--- AGENT THINKING PROCESS ---\n{{logic_log}}</div>
        </div>

        <div class="right-panel">
            <h3>✅ To-Do List</h3>
            <div id="todo-list">
                <div class="task-item">Analyze Page DOM</div>
                <div class="task-item">Identify Target</div>
                <div class="task-item">Execute Interaction</div>
            </div>
        </div>

        <script>
            setInterval(() => {
                fetch('/get_logs').then(r => r.text()).then(t => {
                    const term = document.getElementById('terminal');
                    term.innerText = t;
                    term.scrollTop = term.scrollHeight;
                });
            }, 2000);
        </script>
    </body>
    </html>
    """, logic_log=logic_log, inst=open(INST_PATH).read() if os.path.exists(INST_PATH) else "")

@app.route('/update_inst', methods=['POST'])
def update_inst():
    with open(INST_PATH, 'w') as f: f.write(request.form.get('inst'))
    if os.path.exists(LOG_PATH): os.remove(LOG_PATH) # Clear old logs for new goal
    return """<script>window.location.href='/';</script>"""

@app.route('/get_logs')
def get_logs():
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f: return f.read()
    return "Waiting for agent..."

def gen_frames():
    while True:
        try:
            if os.path.exists(SCREENSHOT_PATH):
                with open(SCREENSHOT_PATH, 'rb') as f: yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + f.read() + b'\r\n')
        except: pass
        time.sleep(0.1)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)