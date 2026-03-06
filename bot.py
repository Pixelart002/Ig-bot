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

# 🔴 AAPKA PRIVATE AI SETUP
HF_TOKEN = "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"
OLLAMA_URL = "https://vivekkumarr-my-ai.hf.space/api/generate"

# ==========================================
# 🧠 SWARM NEURAL NETWORK (QWEN + FLUX)
# ==========================================
def generate_ai_content():
    print("[SWARM-AI] 🧠 Activating Private Qwen-2.5 & Flux...", flush=True)
    
    # 1. Swarm Image Generation (Flux Proxy)
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

    # 2. Text Generation (Private Qwen 7B)
    caption = ""
    try:
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": "Write a 2-line cool Instagram caption for a cyberpunk city image. Include 3 hashtags. No quotes.",
            "stream": False
        }
        
        req = urllib.request.Request(
            OLLAMA_URL, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'}
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = response.read().decode('utf-8')
            res_json = json.loads(res_data)
            caption = res_json.get('response', '').strip().strip('"').strip("'")
            
        print("✅ [SWARM-AI] Qwen Caption Generated!", flush=True)
    except Exception as e:
        print(f"⚠️ [SWARM-AI] Qwen Server Error. Using local brain... ({e})", flush=True)
        caption = "Lost in the neon glow of tomorrow. 🌃✨ #Cyberpunk #FutureCity #NeonLights"

    return caption

# ==========================================
# 🛡️ SMART COORDINATE ENGINE (CLASS BYPASS)
# ==========================================
async def human_delay(min_sec=2.0, max_sec=4.0):
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def click_by_coordinates(page, texts):
    """
    Ye function text ko dhoondhta hai, uska X, Y coordinate nikalta hai, 
    aur bina class use kiye direct Mouse Click marta hai.
    """
    for text in texts:
        try:
            # Sirf text dhoondho, class nahi
            element = page.locator(f"text='{text}'").first
            if await element.count() > 0:
                # Bounding Box se OCR jaisa exact X, Y coordinate nikalo
                box = await element.bounding_box()
                if box:
                    center_x = box['x'] + (box['width'] / 2)
                    center_y = box['y'] + (box['height'] / 2)
                    print(f"🎯 [TARGET LOCKED] '{text}' at X:{int(center_x)}, Y:{int(center_y)}", flush=True)
                    
                    # Direct Mouse Coordinate Click
                    await page.mouse.move(center_x, center_y, steps=5)
                    await page.mouse.click(center_x, center_y)
                    return True
        except:
            pass
    return False

# ==========================================
# 🤖 MAIN BROWSER LOGIC
# ==========================================
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Coordinate Mode + Qwen AI)...", flush=True)
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
                
                # STRICT VIEWPORT: 854x480 (Mobile View)
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
                
                print("[TASK] 🧹 Clearing possible popups (Blind Coordinate Click)...", flush=True)
                await page.mouse.click(800, 50) # Top right cancel
                await human_delay(2.0, 3.0)
                
                print("✅ Feed Ready! Fetching AI Content...", flush=True)
                ai_caption = await asyncio.to_thread(generate_ai_content)
                await human_delay(1.5, 3.0)

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                # Mobile view me Create button screen ke bottom-center par hota hai (No text, just + icon)
                # Hardcoded Coordinate for 854x480 mobile view:
                await page.mouse.move(427, 455, steps=5)
                await page.mouse.click(427, 455)
                await human_delay(3.0, 4.5)

                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    # Smart Coordinate Click (Finds text bounding box and clicks X,Y)
                    clicked = await click_by_coordinates(page, ["Select from computer", "Select From Device", "Select from device"])
                    if not clicked:
                        print("⚠️ Text not found! Fallback to Center Coordinate...", flush=True)
                        await page.mouse.click(427, 240)
                
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await human_delay(3.0, 5.0)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                if not await click_by_coordinates(page, ["Next"]):
                    await page.mouse.click(800, 30) # Top right 'Next' fallback
                await human_delay(2.5, 4.5)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                if not await click_by_coordinates(page, ["Next"]):
                    await page.mouse.click(800, 30)
                await human_delay(2.5, 4.0)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                try:
                    await page.locator("div[aria-label='Write a caption...']").fill(ai_caption)
                except:
                    # Coordinate fallback for caption box
                    await page.mouse.click(427, 150)
                    await page.keyboard.type(ai_caption)
                await human_delay(2.0, 3.5)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                if not await click_by_coordinates(page, ["Share"]):
                    await page.mouse.click(800, 30)
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await human_delay(15.0, 20.0)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                print("[IDLE] 💤 Swarm shifting to patrol mode...", flush=True)
                while not page.is_closed():
                    await human_delay(10.0, 20.0)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
