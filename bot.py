import asyncio
import os
import urllib.request
import base64
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

POST_IMAGE_PATH = "/tmp/ai_post.jpg"
STREAM_PATH = "/tmp/stream.jpg"

async def dismiss_popups(page):
    print("[TASK] 🧹 Clearing popups...", flush=True)
    popups = ["Not Now", "Cancel", "Skip", "Accept"]
    for text in popups:
        try:
            btn = page.locator(f"button:has-text('{text}')")
            if await btn.count() > 0:
                await btn.first.click(timeout=3000, force=True)
                await asyncio.sleep(2)
        except Exception:
            pass

async def browser_logic():
    print("\n[START] 🚀 Booting Swarm Agent (Low-RAM CDP Mode)...", flush=True)
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
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                context.set_default_timeout(60000)
                page = await context.new_page()
                await stealth_async(page)
                
                # CDP SCREENCAST (Zero extra RAM Video Stream)
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
                await asyncio.sleep(8)
                
                for _ in range(2):
                    await dismiss_popups(page)
                
                print("✅ Navigation Complete! Starting Auto-Post PRD...", flush=True)
                await asyncio.sleep(3)

                print("[AI] 🧠 Generating Dummy Image & Caption...", flush=True)
                urllib.request.urlretrieve("https://picsum.photos/600/600", POST_IMAGE_PATH)
                ai_caption = "Hello World! 🌍 Uploaded fully autonomously by my AI Swarm Agent running on 512MB RAM! #AI #Bot #Automation"
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

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_text("Next").first.click()
                await asyncio.sleep(3)

                print("[ACTION] 👉 Clicking Next...", flush=True)
                await page.get_by_text("Next").first.click()
                await asyncio.sleep(3)

                print("[ACTION] ✍️ Typing Caption...", flush=True)
                await page.locator("div[aria-label='Write a caption...']").fill(ai_caption)
                await asyncio.sleep(2)

                print("[ACTION] 🚀 Clicking SHARE!", flush=True)
                await page.get_by_text("Share").click()
                
                print("[WAIT] ⏳ Waiting for upload...", flush=True)
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
