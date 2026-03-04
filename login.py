import asyncio
from playwright.async_api import async_playwright
import time

async def run():
    async with async_playwright() as p:
        user = input("👉 Enter Instagram Username: ")
        pw = input("👉 Enter Instagram Password: ")
        
        print("🚀 Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = await context.new_page()
        
        await page.goto("https://www.instagram.com/accounts/login/")
        await page.fill('input[name="username"]', user)
        await page.fill('input[name="password"]', pw)
        await page.click('button[type="submit"]')
        
        print("⏳ Logging in... 15 seconds wait kar rahe hain (Verification ke liye)...")
        time.sleep(15) 
        
        # Check if login was successful
        await context.storage_state(path="state.json")
        print("✅ SUCCESS! 'state.json' ban gayi hai.")
        await browser.close()

asyncio.run(run())
