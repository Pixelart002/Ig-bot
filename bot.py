import asyncio
import os
import urllib.request
import urllib.parse
import base64
import json
import time
import random
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

POST_IMAGE_PATH = "/tmp/ai_post.jpg"
STREAM_PATH = "/tmp/stream.jpg"

# ==========================================
# 🧠 SWARM NEURAL NETWORK (AI ENDPOINTS)
# ==========================================
def generate_ai_content():
    print("[SWARM-AI] 🧠 Activating Neural Endpoints...", flush=True)
    caption = "Hello World! 🌍 Uploaded fully autonomously by my AI Swarm Agent! #AI #Bot #Automation"
    
    try:
        prompt = "A stunning futuristic cyberpunk city with glowing neon lights, 8k resolution, highly detailed"
        encoded_prompt = urllib.parse.quote(prompt)
        timestamp = int(time.time() * 1000)
        flux_url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={encoded_prompt}&t={timestamp}"

        req = urllib.request.Request(flux_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(POST_IMAGE_PATH, "wb") as f:
                f.write(response.read())
        print("✅ [SWARM-AI] High-Fidelity Flux Image Synthesized!", flush=True)
    except Exception as e:
        print(f"🛑 [SWARM-AI] Image Core Error (Using fallback): {e}", flush=True)
        urllib.request.urlretrieve("https://picsum.photos/600/600", POST_IMAGE_PATH)

    try:
        question = "Write a 2-line cool Instagram caption for a cyberpunk city image. Include 3 hashtags. No quotes."
        encoded_question = urllib.parse.quote(question)
        user_id = str(random.randint(10000, 99999))
        mistral_url = f"https://mistral-ai-three.vercel.app/?id={user_id}&question={encoded_question}"

        req = urllib.request.Request(mistral_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = response.read().decode('utf-8')
            try:
                res_json = json.loads(res_data)
                caption = res_json.get('reply', res_json.get('response', str(res_json)))
            except json.JSONDecodeError:
                caption = res_data.strip().strip('"').strip("'")
        print("✅ [SWARM-AI] Mistral Neural Caption Generated!", flush=True)
    except Exception as e:
        print(f"🛑 [SWARM-AI] Text Core Error (Using fallback): {e}", flush=True)

    return caption

# ==========================================
# 🕵️‍♂️ DEVTOOLS SMART SCANNER (SELF-HEALING)
# ==========================================
async def swarm_smart_click(page, keywords, element_types="button, a, svg, div"):
    """
    Ye function DevTools ki tarah DOM ko scan karta hai. 
    Dynamic classes ko ignore karke element ke text ya label se usko pakadta hai
    aur JavaScript ke through force click karta hai.
    """
    print(f"[SCANNER] 🔎 Scanning DOM for: {keywords}...", flush=True)
    
    js_code = f"""
    () => {{
        const elements = document.querySelectorAll('{element_types}');
        const keywords = {keywords};
        for (let el of elements) {{
            const text = (el.innerText || '').toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').toLowerCase();
            
            for (let kw of keywords) {{
                if (text.includes(kw.toLowerCase()) || aria.includes(kw.toLowerCase())) {{
                    console.log("Found matching element with class: " + el.className);
                    el.scrollIntoView();
                    el.click(); // Force DevTools Click
                    return el.className || 'SVG/No-Class';
                }}
            }}
        }}
        return null;
    }}
    """
    
    # Run the DevTools scanner inside the browser
    result = await page.evaluate(js_code)
    if result:
        print(f"✅ [SCANNER] Element found and clicked! Dynamic Class: {result}", flush=True)
        return True
    else:
        print(f"⚠️ [SCANNER] Not found by JS, attempting Playwright fallback...", flush=True)
        return False

# ==========================================
# 🛡️ SWARM STEALTH & MOVEMENT
# ==========================================
async def human_delay(min_sec=2.0, max_sec=5.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def simulate_human_mouse(page):
    try:
        x, y = random.randint(100, 700), random.randint(100, 400)
        await page.mouse.move(x, y, steps=10)
        await asyncio.sleep(random.uniform(0.5, 1.0))
    except:
        pass

async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Smart DevTools Mode)...", flush=True)
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", 
                        "--start-maximized", "--disable-blink-features=AutomationControlled",
                        "--js-flags=--max-old-space-size=200", "--disable-gpu"
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 854, 'height': 480},
                    user_agent="Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36"
                )
                context.set_default_timeout(60000)
                page = await context.new_page()
                await stealth_async(page)
                
                # CDP SCREENCAST
                client = await context.new_cdp_session(page)
                async def handle_screencast(event):
                    try:
                        img_data = base64.b64decode(event["data"])
                        temp_path = STREAM_PATH + ".tmp"
                        with open(temp_path, "wb") as f:
                            f.write(img_data)
                        os.rename(temp_path, STREAM_PATH)
                        await client.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                    except:
                        pass
                
                client.on("Page.screencastFrame", handle_screencast)
                await client.send("Page.startScreencast", {"format": "jpeg", "quality": 20, "maxWidth": 854, "maxHeight": 480})
                
                # --- PRD LOGIC ---
                print("[TASK] 🌐 Navigating to Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                await human_delay(6.0, 9.0)
                
                await simulate_human_mouse(page)
                await swarm_smart_click(page, ["Not Now", "Cancel", "Skip", "Accept"])
                
                print("✅ Feed Ready! Starting Auto-Post...", flush=True)
                await human_delay(2.0, 4.0)

                ai_caption = await asyncio.to_thread(generate_ai_content)
                await human_delay(1.5, 3.0)

                print("[ACTION] 👉 Finding 'Create' button dynamically...", flush=True)
                await simulate_human_mouse(page)
                # 🔥 DevTools Scanner in Action!
                clicked = await swarm_smart_click(page, ["New post", "Create", "New Post"])
                if not clicked:
                    # Absolute Fallback if JS fails
                    await page.locator("svg[aria-label='New post'], a[href='#']").first.click(timeout=8000)
                await human_delay(3.0, 4.5)

                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    # Smart scan for upload button
                    await swarm_smart_click(page, ["Select from computer", "Select From Device", "Select from device"])
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await human_delay(3.0, 5.0)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await swarm_smart_click(page, ["Next"])
                await human_delay(2.5, 4.5)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await swarm_smart_click(page, ["Next"])
                await human_delay(2.5, 4.0)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                await page.locator("div[aria-label='Write a caption...']").fill(ai_caption)
                await human_delay(2.0, 3.5)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await simulate_human_mouse(page)
                await swarm_smart_click(page, ["Share"])
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await page.get_by_text("Your post has been shared.").wait_for(timeout=40000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                await human_delay(4.0, 6.0)
                await swarm_smart_click(page, ["Close"])

                print("[IDLE] 💤 Swarm shifting to patrol mode...", flush=True)
                while not page.is_closed():
                    await simulate_human_mouse(page)
                    await human_delay(10.0, 20.0)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
