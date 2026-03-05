import asyncio
import os
import urllib.request
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

SCREENSHOT_PATH = "/tmp/stream.jpg"
POST_IMAGE_PATH = "/tmp/ai_post.jpg"

# 🔴 BACKGROUND TASK: Stream kabhi freeze nahi hogi
async def stream_frames(page):
    while not page.is_closed():
        try:
            temp_path = SCREENSHOT_PATH + ".tmp"
            await page.screenshot(path=temp_path, type='jpeg', quality=30, timeout=10000)
            os.rename(temp_path, SCREENSHOT_PATH)
        except Exception:
            pass
        await asyncio.sleep(0.2) # 5 FPS

# 🧹 POPUP BYPASS
async def dismiss_popups(page):
    print("[TASK] 🧹 Clearing popups...", flush=True)
    popups = ["Not Now", "Cancel", "Skip", "Accept"]
    for text in popups:
        try:
            btn = page.locator(f"button:has-text('{text}')")
            if await btn.count() > 0:
                await btn.first.click(timeout=3000, force=True)
                print(f"✅ Dismissed '{text}'", flush=True)
                await asyncio.sleep(2)
        except Exception:
            pass

# 🧠 THE FULL PRD ENGINE
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (PRD Mode)...", flush=True)
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", 
                        "--start-maximized", "--disable-blink-features=AutomationControlled"
                    ]
                )
                
                storage = "state.json" if os.path.exists("state.json") else None
                context = await browser.new_context(
                    storage_state=storage, viewport={'width': 1280, 'height': 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                context.set_default_timeout(60000)
                page = await context.new_page()
                await stealth_async(page)
                
                # Stream ko background mein start kar do
                asyncio.create_task(stream_frames(page))
                
                # --- PHASE 1: NAVIGATION & CLEANUP ---
                print("[TASK] 🌐 Navigating to Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                await asyncio.sleep(8) # Wait for complete load
                
                for _ in range(2):
                    await dismiss_popups(page)
                
                print("✅ Navigation Complete! Starting Auto-Post PRD...", flush=True)
                await asyncio.sleep(3)

                # --- PHASE 2: PRD IMPLEMENTATION (POST GENERATION) ---
                print("[AI] 🧠 Generating Dummy Image & Caption...", flush=True)
                urllib.request.urlretrieve("https://picsum.photos/800/800", POST_IMAGE_PATH)
                ai_caption = "Hello World! 🌍 Uploaded fully autonomously by my AI Swarm Agent. #AI #Bot #Automation"
                await asyncio.sleep(2)

                print("[ACTION] 👉 Clicking 'Create'...", flush=True)
                await page.locator("svg[aria-label='New post']").click(timeout=10000)
                await asyncio.sleep(3)

                print("[ACTION] 📂 Uploading Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    await page.get_by_text("Select from computer").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await asyncio.sleep(4)

                print("[ACTION] 👉 Clicking Next (Crop)...", flush=True)
                await page.get_by_text("Next").click()
                await asyncio.sleep(3)

                print("[ACTION] 👉 Clicking Next (Filters)...", flush=True)
                await page.get_by_text("Next").click()
                await asyncio.sleep(3)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                await page.locator("div[aria-label='Write a caption...']").fill(ai_caption)
                await asyncio.sleep(2)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await page.get_by_text("Share").click()
                
                print("[WAIT] ⏳ Waiting for upload to complete...", flush=True)
                await page.get_by_text("Your post has been shared.").wait_for(timeout=30000)
                print("🎉 [SUCCESS] POST IS LIVE!", flush=True)
                
                await asyncio.sleep(5)
                await page.locator("svg[aria-label='Close']").click()

                print("[IDLE] 💤 Agent standby...", flush=True)
                while not page.is_closed():
                    await asyncio.sleep(10)
                    
        except Exception as e:
            print(f"🛑 [CRASH/RESTART] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
