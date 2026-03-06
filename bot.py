import asyncio
import os
import urllib.request
import urllib.parse
import base64
import json
import time
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
        print(f"⚠️ [SWARM-AI] Qwen Error. Using fallback... ({e})", flush=True)
        caption = "Lost in the neon glow of tomorrow. 🌃✨ #Cyberpunk #FutureCity #NeonLights"

    return caption

# ==========================================
# 🤖 REAL-WORLD ADVANCED AUTOMATION
# ==========================================
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Enterprise ARIA Mode)...", flush=True)
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
                
                # 🖥️ FORCE DESKTOP VIEWPORT (1024x768): Splash screen loop se bachane ke liye
                context = await browser.new_context(
                    viewport={'width': 1024, 'height': 768},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                context.set_default_timeout(45000)
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
                
                # --- CORE LOGIC ---
                print("[TASK] 🌐 Navigating to Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                
                # 🛡️ THE FIX: Wait until the actual home feed SVG is visible (means we passed the splash screen)
                print("[WAIT] Waiting for Instagram Feed to fully render...", flush=True)
                await page.locator("svg[aria-label='Home']").first.wait_for(state="visible", timeout=60000)
                
                print("[TASK] 🧹 Clearing Popups...", flush=True)
                for popup in ["Not Now", "Cancel", "Skip", "Accept"]:
                    try:
                        await page.get_by_role("button", name=popup).click(timeout=3000)
                    except: pass
                
                print("✅ Feed Ready! Fetching AI Content...", flush=True)
                ai_caption = await asyncio.to_thread(generate_ai_content)
                await asyncio.sleep(2)

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                # Enterprise Selector: Ignores obfuscated classes, looks strictly for the SVG label
                await page.locator("svg[aria-label='New post']").first.click()
                
                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser(timeout=20000) as fc_info:
                    # Enterprise Selector: Looks for exact button role and text
                    await page.get_by_role("button", name="Select from computer").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await asyncio.sleep(3)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_role("button", name="Next").click()
                await asyncio.sleep(2)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_role("button", name="Next").click()
                await asyncio.sleep(2)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                # Enterprise Selector: Targets the textbox role directly
                await page.get_by_role("textbox", name="Write a caption...").fill(ai_caption)
                await asyncio.sleep(2)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await page.get_by_role("button", name="Share").click()
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await page.get_by_text("Your post has been shared.").wait_for(timeout=30000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                print("[IDLE] 💤 Swarm shifting to patrol mode...", flush=True)
                while not page.is_closed():
                    await asyncio.sleep(20)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
