import asyncio
import os
from playwright.async_api import async_playwright

SCREENSHOT_PATH = "/tmp/stream.jpg"

async def browser_logic():
    print("\n[START] 🚀 Booting Virtual Desktop internally...", flush=True)
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=False,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--start-maximized"]
                )
                
                storage = "state.json" if os.path.exists("state.json") else None
                context = await browser.new_context(
                    storage_state=storage,
                    viewport={'width': 1280, 'height': 720}
                )
                page = await context.new_page()
                
                print("[TASK] 🌐 Navigating to Target...", flush=True)
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                
                scroll_dir = 1
                while not page.is_closed():
                    # Save to temp path to avoid read/write collision
                    temp_path = SCREENSHOT_PATH + ".tmp"
                    await page.screenshot(path=temp_path, type='jpeg', quality=30)
                    os.rename(temp_path, SCREENSHOT_PATH)
                    
                    await page.evaluate(f"window.scrollBy(0, {20 * scroll_dir})")
                    await asyncio.sleep(0.2)
        except Exception as e:
            print(f"🛑 [RESTARTING] {str(e)}", flush=True)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(browser_logic())
