import asyncio
import os
import urllib.request
import urllib.parse
import base64
import json
import time
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_async

POST_IMAGE_PATH = "/tmp/ai_post.jpg"
STREAM_PATH = "/tmp/stream.jpg"

# 🔴 AAPKA PRIVATE AI SETUP
HF_TOKEN = "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"
OLLAMA_URL = "https://vivekkumarr-my-ai.hf.space/api/generate"

# ==========================================
# 🧠 SWARM NEURAL NETWORK (QWEN + FLUX)
# ==========================================
def generate_ai_content():
    print("[SWARM-AI] 🧠 Activating Private Qwen-2.5 & Flux...", flush=True)
    
    # 1. Image Generation
    try:
        prompt = "A stunning futuristic cyberpunk city with glowing neon lights, 8k resolution, highly detailed"
        encoded_prompt = urllib.parse.quote(prompt)
        timestamp = int(time.time() * 1000)
        flux_url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={encoded_prompt}&t={timestamp}"

        req = urllib.request.Request(flux_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(POST_IMAGE_PATH, "wb") as f:
                f.write(response.read())
        print("✅ [SWARM-AI] Image Synthesized!", flush=True)
    except Exception as e:
        print(f"🛑 [SWARM-AI] Image Error: {e}", flush=True)
        urllib.request.urlretrieve("https://picsum.photos/600/600", POST_IMAGE_PATH)

    # 2. Text Generation (Private Qwen)
    caption = ""
    try:
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": "Write a 2-line cool Instagram caption for a cyberpunk city image. Include 3 hashtags. No quotes.",
            "stream": False
        }
        req = urllib.request.Request(
            OLLAMA_URL, data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'}
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = response.read().decode('utf-8')
            caption = json.loads(res_data).get('response', '').strip().strip('"').strip("'")
        print("✅ [SWARM-AI] Qwen Caption Generated!", flush=True)
    except Exception as e:
        print(f"⚠️ [SWARM-AI] Qwen Error. Using local brain... ({e})", flush=True)
        caption = "Lost in the neon glow of tomorrow. 🌃✨ #Cyberpunk #FutureCity #NeonLights"

    return caption

# ==========================================
# 🛡️ ADVANCED REAL-WORLD LOCATOR ENGINE
# ==========================================
async def human_delay(min_sec=1.5, max_sec=3.5):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def smart_click(page, selectors, timeout=10000):
    """Tries a list of robust selectors and clicks the first one that is visible."""
    for selector in selectors:
        try:
            element = page.locator(selector).first
            await element.wait_for(state="visible", timeout=timeout)
            await element.click()
            print(f"🎯 [CLICKED] {selector}", flush=True)
            return True
        except PlaywrightTimeoutError:
            continue
        except Exception as e:
            continue
    return False

# ==========================================
# 🤖 MAIN BROWSER LOGIC
# ==========================================
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Real-World State Mode)...", flush=True)
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
                        with open(STREAM_PATH + ".tmp", "wb") as f:
                            f.write(base64.b64decode(event["data"]))
                        os.rename(STREAM_PATH + ".tmp", STREAM_PATH)
                        await client.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                    except: pass
                
                client.on("Page.screencastFrame", handle_screencast)
                await client.send("Page.startScreencast", {"format": "jpeg", "quality": 20, "maxWidth": 854, "maxHeight": 480})
                
                # --- PRD LOGIC ---
                print("[TASK] 🌐 Navigating to Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                
                # 🛑 THE FIX: Wait specifically for the 'Home' icon to ensure the Splash Screen is gone
                print("[WAIT] ⏳ Bypassing Meta Splash Screen, waiting for feed to load...", flush=True)
                await page.locator("svg[aria-label='Home'], svg[aria-label='home']").first.wait_for(state="visible", timeout=45000)
                print("✅ Feed is fully loaded and visible!", flush=True)
                
                # Dismiss "Use the App" or "Add to Home Screen" popups if they appear
                await smart_click(page, ["button:has-text('Not Now')", "button:has-text('Cancel')"], timeout=3000)
                await human_delay()

                # Generate AI Content concurrently
                ai_caption = await asyncio.to_thread(generate_ai_content)
                await human_delay()

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                # Mobile web specific locators for the "+" icon
                create_locators = [
                    "svg[aria-label='New post']", 
                    "svg[aria-label='New Post']",
                    "a[href='#']:has(svg)", 
                    "[data-testid='new-post-button']"
                ]
                if not await smart_click(page, create_locators):
                    raise Exception("Create button not found after feed loaded!")
                
                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser(timeout=15000) as fc_info:
                    upload_locators = ["button:has-text('Select from computer')", "button:has-text('Select From Device')", "button:has-text('Select from device')"]
                    await smart_click(page, upload_locators)
                
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await human_delay(2.0, 4.0)

                print("[ACTION] 👉 Clicking Next (1/2)...", flush=True)
                await smart_click(page, ["button:has-text('Next')", "div:has-text('Next')"])
                await human_delay()

                print("[ACTION] 👉 Clicking Next (2/2)...", flush=True)
                await smart_click(page, ["button:has-text('Next')", "div:has-text('Next')"])
                await human_delay()

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                caption_box = page.locator("div[aria-label='Write a caption...']").first
                await caption_box.wait_for(state="visible", timeout=10000)
                await caption_box.fill(ai_caption)
                await human_delay()

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await smart_click(page, ["button:has-text('Share')", "div:has-text('Share')"])
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await page.locator("text='Your post has been shared.'").wait_for(state="visible", timeout=45000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                print("[IDLE] 💤 Swarm shifting to patrol mode...", flush=True)
                while not page.is_closed():
                    await human_delay(10.0, 20.0)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
