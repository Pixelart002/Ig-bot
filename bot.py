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
    
    # 1. Swarm Image Generation (Flux Proxy Endpoint)
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

    # 2. Swarm Text Generation (Mistral Proxy Endpoint)
    try:
        question = "Write a 2-line cool Instagram caption for a cyberpunk city image. Include 3 hashtags. No quotes."
        encoded_question = urllib.parse.quote(question)
        user_id = str(random.randint(10000, 99999))
        mistral_url = f"https://mistral-ai-three.vercel.app/?id={user_id}&question={encoded_question}"

        req = urllib.request.Request(mistral_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = response.read().decode('utf-8')
            try:
                # Agar JSON aaya
                res_json = json.loads(res_data)
                caption = res_json.get('reply', res_json.get('response', str(res_json)))
            except json.JSONDecodeError:
                # Agar plain text aaya
                caption = res_data.strip().strip('"').strip("'")
        print("✅ [SWARM-AI] Mistral Neural Caption Generated!", flush=True)
    except Exception as e:
        print(f"🛑 [SWARM-AI] Text Core Error (Using fallback): {e}", flush=True)

    return caption

# ==========================================
# 🛡️ SWARM STEALTH & ANTI-BOT LOGIC
# ==========================================
async def human_delay(min_sec=2.0, max_sec=5.0):
    """Simulates random human thinking time"""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def simulate_human_mouse(page):
    """Simulates human mouse movements to bypass bot detection"""
    try:
        x = random.randint(100, 700)
        y = random.randint(100, 400)
        await page.mouse.move(x, y, steps=15)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await page.mouse.wheel(0, random.choice([-200, 200, 300, -100]))
    except:
        pass

async def dismiss_popups(page):
    print("[TASK] 🧹 Swarm is clearing popups...", flush=True)
    popups = ["Not Now", "Cancel", "Skip", "Accept", "Turn Off"]
    for text in popups:
        try:
            btn = page.locator(f"button:has-text('{text}')")
            if await btn.count() > 0:
                await human_delay(1.0, 2.5)
                await btn.first.click(timeout=3000, force=True)
        except Exception:
            pass

# ==========================================
# 🤖 THE MAIN SWARM BRAIN
# ==========================================
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Ghost Anti-Bot Mode)...", flush=True)
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
                
                # CDP SCREENCAST (Zero extra RAM)
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
                await human_delay(7.0, 10.0)
                
                await simulate_human_mouse(page)
                for _ in range(2):
                    await dismiss_popups(page)
                
                print("✅ Security Bypassed! Starting Auto-Post...", flush=True)
                await human_delay(2.0, 4.0)

                # Fetch AI content asynchronously
                ai_caption = await asyncio.to_thread(generate_ai_content)
                await human_delay(1.5, 3.0)

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                await simulate_human_mouse(page)
                create_btn = page.locator("a:has-text('Create'), a[href='#']:has-text('Create'), svg[aria-label='New post']")
                await create_btn.first.click(timeout=10000)
                await human_delay(2.5, 4.5)

                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    upload_btn = page.locator("button:has-text('Select from computer'), button:has-text('Select From Device')")
                    await upload_btn.first.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await human_delay(3.0, 5.0)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_text("Next").first.click()
                await human_delay(2.5, 4.5)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_text("Next").first.click()
                await human_delay(2.5, 4.0)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                await page.locator("div[aria-label='Write a caption...']").fill(ai_caption)
                await human_delay(2.0, 3.5)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await simulate_human_mouse(page)
                await page.get_by_text("Share").click()
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await page.get_by_text("Your post has been shared.").wait_for(timeout=40000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                await human_delay(4.0, 6.0)
                try:
                    await page.locator("svg[aria-label='Close']").click()
                except:
                    pass

                print("[IDLE] 💤 Swarm shifting to patrol mode...", flush=True)
                while not page.is_closed():
                    await simulate_human_mouse(page)
                    await human_delay(10.0, 20.0)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
