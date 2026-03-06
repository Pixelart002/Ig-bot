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
    print("[SWARM-AI] 🧠 Brain working in background...", flush=True)
    try:
        prompt = "A stunning futuristic cyberpunk city with glowing neon lights, 8k resolution, highly detailed"
        encoded_prompt = urllib.parse.quote(prompt)
        timestamp = int(time.time() * 1000)
        flux_url = f"https://flux-schnell.hello-kaiiddo.workers.dev/img?prompt={encoded_prompt}&t={timestamp}"

        req = urllib.request.Request(flux_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(POST_IMAGE_PATH, "wb") as f:
                f.write(response.read())
    except:
        urllib.request.urlretrieve("https://picsum.photos/600/600", POST_IMAGE_PATH)

    caption = ""
    try:
        payload = {"model": "qwen2.5-coder:7b", "prompt": "Write a 2-line cool Instagram caption for a cyberpunk city image. Include 3 hashtags. No quotes.", "stream": False}
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'})
        with urllib.request.urlopen(req, timeout=30) as response:
            res_json = json.loads(response.read().decode('utf-8'))
            caption = res_json.get('response', '').strip().strip('"').strip("'")
    except:
        caption = "Lost in the neon glow of tomorrow. 🌃✨ #Cyberpunk #FutureCity"
    
    print("✅ [SWARM-AI] Content Ready!", flush=True)
    return caption

# ==========================================
# ⚡ TURBO BROWSER ENGINE
# ==========================================
async def block_heavy_resources(route):
    # Block videos, fonts, and heavy tracking to speed up loading 5x
    if route.request.resource_type in ["media", "font"]:
        await route.abort()
    else:
        await route.continue_()

async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (TURBO MODE)...", flush=True)
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
                
                # 🔥 STATE.JSON LOADED: Instant Login Bypass
                context_args = {
                    "viewport": {'width': 1024, 'height': 768},
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                if os.path.exists("state.json"):
                    context_args["storage_state"] = "state.json"
                    
                context = await browser.new_context(**context_args)
                context.set_default_timeout(30000)
                page = await context.new_page()
                await stealth_async(page)
                
                # Activate Turbo Network Interceptor
                await page.route("**/*", block_heavy_resources)
                
                # CDP SCREENCAST (Low impact)
                client = await context.new_cdp_session(page)
                async def handle_screencast(event):
                    try:
                        temp_path = STREAM_PATH + ".tmp"
                        with open(temp_path, "wb") as f:
                            f.write(base64.b64decode(event["data"]))
                        os.rename(temp_path, STREAM_PATH)
                        await client.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
                    except: pass
                client.on("Page.screencastFrame", handle_screencast)
                await client.send("Page.startScreencast", {"format": "jpeg", "quality": 10, "maxWidth": 854, "maxHeight": 480})
                
                # ⚡ PARALLEL EXECUTION: Start AI generation & Page load at the SAME TIME
                print("[TASK] 🌐 Loading Instagram & AI Brain simultaneously...", flush=True)
                ai_task = asyncio.create_task(asyncio.to_thread(generate_ai_content))
                
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                
                # Wait for main UI to render
                await page.locator("svg[aria-label='Home']").first.wait_for(state="visible", timeout=45000)
                
                # Await AI task just in case it's not done yet
                ai_caption = await ai_task

                print("✅ Feed & AI Ready! Executing Blitzkrieg Post...", flush=True)

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                await page.locator("svg[aria-label='New post']").first.click()
                
                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    await page.get_by_role("button", name="Select from computer").click()
                await (await fc_info.value).set_files(POST_IMAGE_PATH)

                print("[ACTION] 👉 Speed-Clicking Next...", flush=True)
                await page.get_by_role("button", name="Next").click()
                await asyncio.sleep(0.5) # Micro-delay for UI transition
                await page.get_by_role("button", name="Next").click()

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                # Fill is instant compared to typing letter by letter
                await page.get_by_role("textbox", name="Write a caption...").fill(ai_caption)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await page.get_by_role("button", name="Share").click()
                
                print("[WAIT] ⏳ Waiting for upload confirmation...", flush=True)
                await page.get_by_text("Your post has been shared.").wait_for(timeout=30000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                print("[IDLE] 💤 Swarm resting...", flush=True)
                while not page.is_closed():
                    await asyncio.sleep(20)
                    
        except Exception as e:
            print(f"🛑 [SWARM CRASH] {str(e)}", flush=True)
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(browser_logic())
