import asyncio, os, urllib.request, json, time, base64
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# CONFIG
HF_TOKEN = "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"
OLLAMA_URL = "https://vivekkumarr-my-ai.hf.space/api/generate"
LOG_PATH = "/tmp/swarm_logic.txt"
STREAM_PATH = "/tmp/stream.jpg"
INST_PATH = "instructions.txt"

# Anti-Link Formatting Trick
DEFAULT_URL = "https://" + "www.google.com"

def swarm_log(msg):
    print(f"[MANUS] {msg}", flush=True)
    with open(LOG_PATH, "a") as f: f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

# 🟢 AI request ko background thread me chalane ke liye (System Prompt Add Kiya)
def fetch_ai_decision_sync(prompt, system_prompt):
    payload = {
        "model": "qwen2.5-coder:1.5b", 
        "prompt": prompt, 
        "system": system_prompt, # 🔥 NAYA: Kadak System Prompt bheja ja raha hai
        "stream": True,
        "options": {
            "num_ctx": 4096, # RAM SAVER
            "temperature": 0.1
        }
    }
    req = urllib.request.Request(
        OLLAMA_URL, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'},
        method='POST'
    )
    full_response = ""
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            for line in r:
                line = line.decode('utf-8').strip()
                if line:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            full_response += chunk['response']
                    except Exception:
                        pass
    except Exception as e:
        print(f"API Error: {e}")
    return full_response

async def get_dom_map(page):
    try:
        return await page.evaluate("""
            () => {
                const items = [];
                const interactive = document.querySelectorAll('button, a, input, textarea');
                interactive.forEach((el, i) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.y >= 0) {
                        items.push({ 
                            id: i,
                            tag: el.tagName,
                            text: (el.innerText || el.getAttribute('aria-label') || el.placeholder || '').substring(0, 20).replace(/\\n/g, ' '),
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2)
                        });
                    }
                });
                return items.slice(0, 10);
            }
        """)
    except Exception as e:
        swarm_log(f"⚠️ DOM Mapping mein dikkat: {e}")
        return []

async def think_and_act(page, goal):
    dom_elements = await get_dom_map(page)
    url = page.url
    
    # 🔥 NAYA: Bada aur strict System Prompt jo AI ko bhatakne nahi dega
    system_prompt = """You are an elite, strict web automation AI. Your ONLY job is to achieve the user's GOAL.
CRITICAL RULES:
1. ABSOLUTE OBEDIENCE: Do exactly what the GOAL says. Do NOT guess or click random buttons.
2. URL NAVIGATION: If the GOAL is a domain name (e.g., 'luviio.in', 'youtube.com'), your VERY FIRST action MUST be 'navigate' to 'https://[domain]'.
3. JSON ONLY: You must respond ONLY with valid JSON. No markdown, no explanations, no extra text.
4. DOUBLE QUOTES: Use double quotes for all JSON keys and values.
5. FINISH: When the goal is met, output action 'finish'."""

    # Prompt ko chota aur clean kar diya kyunki rules ab System Prompt mein hain
    prompt = f"""Goal: {goal}
Current URL: {url}
Visible Elements: {json.dumps(dom_elements)}

Respond strictly in this JSON FORMAT:
{{"action": "click/type/navigate/finish", "x": 0, "y": 0, "text": "", "url": "", "thought": "Short reason"}}"""

    try:
        # System prompt ko API request mein pass kar rahe hain
        full_response = await asyncio.to_thread(fetch_ai_decision_sync, prompt, system_prompt)
        clean_res = full_response.strip()
        
        if "```json" in clean_res:
            clean_res = clean_res.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_res:
            clean_res = clean_res.split("```")[1].strip()
        
        start_idx = clean_res.find('{')
        end_idx = clean_res.rfind('}') + 1
        
        if start_idx != -1 and end_idx != 0:
            clean_res = clean_res[start_idx:end_idx]
        else:
            clean_res = '{}'
        
        decision = json.loads(clean_res)
        swarm_log(f"🧠 Soch: {decision.get('thought', 'Action le raha hoon...')}")
        
        action = decision.get('action')
        if action == 'click':
            await page.mouse.click(decision['x'], decision['y'])
        elif action == 'type':
            await page.mouse.click(decision['x'], decision['y'])
            await page.keyboard.type(decision['text'])
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
        elif action == 'navigate':
            # Check if URL needs formatting
            target_url = decision['url']
            if not target_url.startswith('http'):
                target_url = 'https://' + target_url
            swarm_log(f"🌐 Naye URL par jaa rahe hain: {target_url}")
            await page.goto(target_url)
        elif action == 'finish':
            swarm_log("🎯 KAAM POORA HO GAYA!")
            return True
            
    except Exception as e:
        swarm_log(f"🛑 Faisla lene mein Error: {e}")
        
    return False

def save_frame_sync(data):
    try:
        with open(STREAM_PATH, "wb") as f: 
            f.write(base64.b64decode(data))
    except: pass

async def browser_logic():
    swarm_log("🚀 MANUS AGENT INITIALIZING (24/7 MODE)...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, 
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--mute-audio" 
            ]
        )
        # 🔥 FIX: locale='en-US' add kiya taaki har website sirf English mein khule!
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
            timezone_id='America/New_York'
        )
        page = await context.new_page()
        await stealth_async(page)

        client = await context.new_cdp_session(page)
        async def handle_screencast(event):
            await asyncio.to_thread(save_frame_sync, event["data"])
            try:
                await client.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            except: pass
            
        client.on("Page.screencastFrame", handle_screencast)
        await client.send("Page.startScreencast", {
            "format": "jpeg", 
            "quality": 10,
            "everyNthFrame": 2
        })

        swarm_log("🌐 Default browser page khol rahe hain...")
        await page.goto(DEFAULT_URL)
        swarm_log("💤 Agent is ONLINE 24/7 and waiting for tasks...")

        while True:
            if os.path.exists(INST_PATH):
                with open(INST_PATH, 'r') as f: goal = f.read().strip()
                if goal:
                    swarm_log(f"🎯 NAYA GOAL MILA: {goal}")
                    
                    for _ in range(15):
                        done = await think_and_act(page, goal)
                        if done: break
                        await asyncio.sleep(1.5)
                    
                    swarm_log("✅ Kaam khatam! Waiting for next instruction...")
                    if os.path.exists(INST_PATH): os.remove(INST_PATH)
            
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(browser_logic())