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

async def get_dom_map(page):
    try:
        # 🔥 DIET DOM: Kam elements aur trim kiya hua text bhejo
        return await page.evaluate("""
            () => {
                const items = [];
                const interactive = document.querySelectorAll('button, a, input, textarea');
                interactive.forEach((el, i) => {
                    const rect = el.getBoundingClientRect();
                    // Sirf wahi elements lo jo screen par properly visible hain
                    if (rect.width > 0 && rect.height > 0 && rect.y >= 0) {
                        items.push({ 
                            id: i,
                            tag: el.tagName,
                            // 🔥 TEXT TRIMMING: AI ka time bachane ke liye sirf 20 words
                            text: (el.innerText || el.getAttribute('aria-label') || el.placeholder || '').substring(0, 20).replace(/\\n/g, ' '),
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2)
                        });
                    }
                });
                // 🔥 TOP 10 ITEMS ONLY (Memory bachane ke liye)
                return items.slice(0, 10);
            }
        """)
    except Exception as e:
        swarm_log(f"⚠️ DOM Mapping mein dikkat: {e}")
        return []

async def think_and_act(page, goal):
    dom_elements = await get_dom_map(page)
    url = page.url
    
    # 🔥 ULTRA SHORT PROMPT: AI fatafat padh kar reply dega
    prompt = f"""Goal:{goal}. URL:{url}. Elements:{json.dumps(dom_elements)}.
Respond ONLY in JSON format: {{"action": "click/type/navigate/finish", "x": 0, "y": 0, "text": "", "url": "", "thought": "Short reason"}}"""

    try:
        # 🔥 Stream: True rakha hai aur Context Window 32K hai
        payload = {
            "model": "qwen2.5-coder:1.5b", 
            "prompt": prompt, 
            "stream": True,
            "options": {
                "num_ctx": 32768
            }
        }
        
        # 🔥 POST request bhej rahe hain
        req = urllib.request.Request(
            OLLAMA_URL, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'},
            method='POST'
        )
        
        full_response = ""
        
        # Stream padhne ka naya tareeqa
        with urllib.request.urlopen(req, timeout=120) as r:
            for line in r:
                line = line.decode('utf-8').strip()
                if line:
                    try:
                        # Har ek tukde ko alag parse karenge
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            full_response += chunk['response']
                    except Exception as parse_err:
                        # Agar koi line kharab aati hai toh ignore kardo
                        pass
        
        clean_res = full_response.strip()
        
        # Markdown parser fallback
        if "```json" in clean_res:
            clean_res = clean_res.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_res:
            clean_res = clean_res.split("```")[1].strip()
        
        # 🟢 Ultimate JSON Extractor: Faltu baaton ko hata do
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
        elif action == 'navigate':
            swarm_log(f"🌐 Naye URL par jaa rahe hain: {decision['url']}")
            await page.goto(decision['url'])
        elif action == 'finish':
            swarm_log("🎯 KAAM POORA HO GAYA!")
            return True
            
    except Exception as e:
        swarm_log(f"🛑 Faisla lene mein Error: {e}")
        
    return False

async def browser_logic():
    swarm_log("🚀 MANUS AGENT START HO RAHA HAI...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        await stealth_async(page)

        client = await context.new_cdp_session(page)
        async def handle_screencast(event):
            try:
                with open(STREAM_PATH, "wb") as f: f.write(base64.b64decode(event["data"]))
                await client.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            except: pass
        client.on("Page.screencastFrame", handle_screencast)
        await client.send("Page.startScreencast", {"format": "jpeg", "quality": 15})

        swarm_log("🌐 Default browser page khol rahe hain...")
        await page.goto(DEFAULT_URL)

        while True:
            if os.path.exists(INST_PATH):
                with open(INST_PATH, 'r') as f: goal = f.read().strip()
                if goal:
                    swarm_log(f"🎯 NAYA GOAL MILA: {goal}")
                    for _ in range(15):
                        done = await think_and_act(page, goal)
                        if done: break
                        await asyncio.sleep(4)
                    
                    if os.path.exists(INST_PATH): os.remove(INST_PATH)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())