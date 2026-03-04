import requests, time, threading
from flask import Flask
app = Flask(__name__)
@app.route('/')
def health(): return {"status": "Aether-Swarm Active"}

def autonomous_swarm():
    while True:
        try:
            print("🧠 Swarm is thinking...")
            # Mistral + Flux + Pinchtab logic yahan trigger hogi
            time.sleep(3600)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=autonomous_swarm, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
