import asyncio
import os
import urllib.request
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

SCREENSHOT_PATH = "/tmp/stream.jpg"
POST_IMAGE_PATH = "/tmp/ai_generated_post.jpg"

# 🔴 BACKGROUND TASK: Ye aapki live stream ko continuously chalata rahega
async def stream_frames(page):
    while not page.is_closed():
        try:
            temp_path = SCREENSHOT_PATH + ".tmp"
            await page.screenshot(path=temp_path, type='jpeg', quality=40, timeout=10000)
            os.rename(temp_path, SCREENSHOT_PATH)
        except Exception:
            pass
        await asyncio.sleep(0.2)

# 🧹 POPUP BYPASS
async def dismiss_popups(page):
    print("[TASK] 🧹 Clearing Instagram popups...", flush=True)
    popups_to_click = ["Not Now", "Cancel", "Skip", "Accept"]
    for text in popups_to_click:
        try:
            btn = page.locator(f"button:has-text('{text}'), div[role='button']:has-text('{text}')")
            if await btn.count() > 0:
                await btn.first.click(timeout=3000, force=True)
                print(f"✅ Clicked '{text}'", flush=True)
                await asyncio.sleep(2) 
        except Exception:
            pass

# 🧠 THE PRD ENGINE: Auto-Post Logic
async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Production Mode)...", flush=True)
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
                
                # 1. Start Live Streaming Task (Video kabhi nahi rukegi)
                asyncio.create_task(stream_frames(page))
                
                print("[TASK] 🌐 Navigating to Instagram...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                await asyncio.sleep(5) 
                
                # 2. Clear Popups
                for _ in range(2):
                    await dismiss_popups(page)
                
                # ---------------------------------------------------------
                # 🚀 PHASE 2: PRD IMPLEMENTATION (POST GENERATION & UPLOAD)
                # ---------------------------------------------------------
                print("✅ Main Feed Ready! Initiating PRD Upload Protocol...", flush=True)
                await asyncio.sleep(2)

                # STEP A: Generate AI Content (Using Dummy Image & Text for now)
                print("[AI] 🧠 Generating Image and Caption...", flush=True)
                urllib.request.urlretrieve("https://picsum.photos/800/800", POST_IMAGE_PATH)
                ai_caption = "Hello World! 🌍 This post was 100% autonomously generated and uploaded by my Cloud Swarm Agent. #AI #Automation #Bot #Future"
                await asyncio.sleep(2) # Give viewer time to see what's happening

                # STEP B: Click "Create" (Sidebar)
                print("[ACTION] 👉 Clicking 'Create' Button...", flush=True)
                await page.locator("svg[aria-label='New post']").click(timeout=10000)
                await asyncio.sleep(2)

                # STEP C: File Upload Intercept
                print("[ACTION] 📂 Selecting Image...", flush=True)
                async with page.expect_file_chooser() as fc_info:
                    await page.get_by_text("Select from computer").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(POST_IMAGE_PATH)
                await asyncio.sleep(3)

                # STEP D: Click Next (Bypass Crop)
                print("[ACTION] 👉 Clicking Next (Crop)...", flush=True)
                await page.get_by_text("Next").first.click()
                await asyncio.sleep(2)

                # STEP E: Click Next (Bypass Filters)
                print("[ACTION] 👉 Clicking Next (Filters)...", flush=True)
                await page.get_by_text("Next").first.click()
                await asyncio.sleep(2)

                # STEP F: Write Caption
                print("[ACTION] ✍️ Typing AI Caption...", flush=True)
                await page.locator('div[aria-label="Write a caption..."]').fill(ai_caption)
                await asyncio.sleep(3)

                # STEP G: Share
                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await page.get_by_text("Share").first.click()
                
                # STEP H: Wait for upload success
                print("[WAIT] ⏳ Uploading to Instagram servers...", flush=True)
                await page.locator("text=Your post has been shared.").wait_for(timeout=30000)
                print("🎉 [SUCCESS] PRD COMPLETE! Post is live on Instagram!", flush=True)
                
                # Close the success modal
                await asyncio.sleep(3)
                await page.locator("svg[aria-label='Close']").first.click()

                # Done! Now just chill and keep the stream alive
                print("[IDLE] Agent going into standby mode. Watching feed...", flush=True)
                while not page.is_closed():
                    await asyncio.sleep(10)
                    
        except Exception as e:
            print(f"🛑 [CRASH] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
