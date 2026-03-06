cat << 'EOF' > bot.py
import asyncio, os, urllib.request, json, time, base64
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# CONFIG
HF_TOKEN = "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"
OLLAMA_URL = "https://vivekkumarr-my-ai.hf.space/api/generate"
LOG_PATH = "/tmp/swarm_logic.txt"
STREAM_PATH = "/tmp/stream.jpg"
INST_PATH = "instructions.txt"

def swarm_log(msg):
    print(f"[MANUS] {msg}", flush=True)
    with open(LOG_PATH, "a") as f: f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

async def get_dom_map(page):
    try:
        # 🟢 Yahan .push() use hua hai, .append() nahi!
        return await page.evaluate("""
            () => {
                const items = [];
                const interactive = document.querySelectorAll('button, a, input, [role="button"], textarea');
                interactive.forEach((el, i) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        items.push({ 
                            id: i,
                            tag: el.tagName,
                            text: el.innerText || el.getAttribute('aria-label') || el.placeholder || '',
                            x: rect.x + rect.width/2,
                            y: rect.y + rect.height/2
                        });
                    }
                });
                return items.slice(0, 30);
            }
        """)
    except Exception as e:
        swarm_log(f"⚠️ DOM Mapping issue: {e}")
        return []

async def think_and_act(page, goal):
    dom_elements = await get_dom_map(page)
    url = page.url
    
    prompt = f"""
    GOAL: {goal}
    CURRENT URL: {url}
    PAGE ELEMENTS: {json.dumps(dom_elements)}
    
    You are an autonomous browser agent. Decide the next action based on elements.
    Respond ONLY in valid JSON:
    {{"action": "click", "x": 100, "y": 200, "thought": "Reasoning here"}}
    OR
    {{"action": "type", "text": "hello", "x": 100, "y": 200, "thought": "Reasoning here"}}
    OR
    {{"action": "navigate", "url": "https://...", "thought": "Reasoning here"}}
    OR
    {{"action": "finish", "thought": "Goal achieved"}}
    """

    try:
        payload = {"model": "qwen2.5-coder:7b", "prompt": prompt, "stream": False}
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode('utf-8'), 
                                    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'})
        with urllib.request.urlopen(req, timeout=60) as r:
            res_raw = r.read().decode('utf-8')
            res = json.loads(res_raw)
            clean_res = res.get('response', '{}').strip()
            if "```json" in clean_res:
                clean_res = clean_res.split("```json")[1].split("```")[0].strip()
            
            decision = json.loads(clean_res)
            swarm_log(f"🧠 THOUGHT: {decision.get('thought')}")
            
            action = decision.get('action')
            if action == 'click':
                await page.mouse.click(decision['x'], decision['y'])
            elif action == 'type':
                await page.mouse.click(decision['x'], decision['y'])
                await page.keyboard.type(decision['text'])
                await page.keyboard.press("Enter")
            elif action == 'navigate':
                await page.goto(decision['url'])
            elif action == 'finish':
                swarm_log("🎯 GOAL ACHIEVED!")
                return True
    except Exception as e:
        swarm_log(f"🛑 Decision Error: {e}")
    return False

async def browser_logic():
    swarm_log("🚀 MANUS AGENT INITIALIZING...")
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

        while True:
            if os.path.exists(INST_PATH):
                with open(INST_PATH, 'r') as f: goal = f.read().strip()
                if goal:
                    swarm_log(f"🎯 NEW GOAL DETECTED: {goal}")
                    if "http" not in page.url: 
                        await page.goto("[https://www.google.com](https://www.google.com)")
                    
                    for _ in range(15):
                        done = await think_and_act(page, goal)
                        if done: break
                        await asyncio.sleep(4)
                    
                    if os.path.exists(INST_PATH): os.remove(INST_PATH)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
EOF