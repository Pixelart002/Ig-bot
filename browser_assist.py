#!/usr/bin/env python3
"""
Instagram Signup Bot using Lightpanda CDP
Complete state-machine implementation of the given pseudo code.
"""

import asyncio
import logging
import sys
import time
from typing import Optional, Dict, Any

from lightpanda import Browser  # pip install lightpanda

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class SignupBot:
    """Instagram signup automation with Lightpanda."""

    def __init__(self, headless: bool = False, timeout: int = 30):
        self.headless = headless
        self.timeout = timeout
        self.browser: Optional[Browser] = None
        self.page = None
        self.state = "INIT"
        self.user_data: Dict[str, Any] = {}

    async def start(self):
        """Launch browser and open signup page."""
        logger.info("🚀 Starting browser...")
        self.browser = await Browser.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        self.page = await self.browser.new_page()
        logger.info("✅ Browser launched.")

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
            logger.info("🔒 Browser closed.")

    async def open_signup_page(self):
        """Open Instagram signup URL."""
        url = "https://www.instagram.com/accounts/emailsignup/"
        logger.info(f"🌐 Opening signup page: {url}")
        await self.page.goto(url, wait_until="networkidle2", timeout=self.timeout * 1000)
        self.state = "PAGE_LOADED"
        logger.info("✅ Signup page loaded.")

    async def wait_for_signup_form(self):
        """Wait until the email input is present."""
        logger.info("⏳ Waiting for signup form...")
        await self.page.wait_for_selector('input[name="emailOrPhone"]', timeout=self.timeout * 1000)
        self.state = "FORM_READY"
        logger.info("✅ Form ready.")

    async def fill_email_and_submit(self, email: str):
        """Type email and click submit."""
        logger.info(f"📧 Filling email: {email}")
        await self.page.type('input[name="emailOrPhone"]', email, delay=50)
        await asyncio.sleep(1)  # slight pause
        # Click the submit button
        await self.page.click('button[type="submit"]')
        self.state = "EMAIL_SUBMITTED"
        logger.info("✅ Email submitted.")

    async def wait_for_state_change(self):
        """Wait for any change in page state (e.g., OTP, password, etc.)."""
        logger.info("⏳ Waiting for next screen...")
        # We'll just wait a few seconds and then let the main loop detect state.
        await asyncio.sleep(3)

    async def get_current_state(self) -> str:
        """Determine the current page state based on visible elements."""
        content = await self.page.content()
        # Check for OTP
        if "Enter the code" in content or "Confirmation Code" in content or \
           await self.page.query_selector('input[name="verificationCode"]'):
            return "OTP"
        # Check for password
        if await self.page.query_selector('input[name="password"]'):
            return "PASSWORD"
        # Check for birthday
        if "Date of birth" in content or await self.page.query_selector('select[name="birthday_day"]'):
            return "BIRTHDAY"
        # Check for profile
        if "Create a profile" in content or "Add a profile" in content or \
           await self.page.query_selector('input[name="fullName"]'):
            return "PROFILE"
        # Check for terms
        if "Terms and Conditions" in content or "Accept terms" in content or "Privacy Policy" in content:
            return "TERMS"
        # Check for success
        if "Welcome to Instagram" in content or "You're all set" in content or \
           "Continue as" in content or await self.page.query_selector('main > div[role="button"]'):
            return "SUCCESS"
        # Check for error
        if "Sorry, this page isn't available" in content or "Try again later" in content or "Blocked" in content:
            return "ERROR"
        return "UNKNOWN"

    async def handle_otp(self) -> bool:
        """
        Handle OTP screen.
        Returns True if verification succeeded, False if failed.
        """
        self.state = "WAITING_FOR_OTP"
        logger.info("📱 OTP verification required.")
        logger.info("👉 Please enter the OTP manually in the browser and submit.")
        logger.info("⏳ Waiting for verification to complete (manual action)...")

        # Wait until the page changes (password screen or profile etc.)
        # We'll wait for a maximum of 5 minutes.
        try:
            await self.page.wait_for_function(
                """
                () => {
                    const body = document.body.innerText;
                    return body.includes('Password') ||
                           body.includes('Create a profile') ||
                           document.querySelector('input[type="password"]') !== null ||
                           body.includes('Welcome to Instagram');
                }
                """,
                timeout=300000  # 5 minutes
            )
            logger.info("✅ OTP verification succeeded.")
            return True
        except Exception:
            logger.error("❌ OTP verification failed (timeout or error).")
            return False

    async def handle_password(self, password: str):
        """Fill password and submit."""
        logger.info("🔑 Setting password...")
        await self.page.wait_for_selector('input[name="password"]', timeout=5000)
        await self.page.type('input[name="password"]', password, delay=50)
        await self.page.click('button[type="submit"]')
        self.state = "PASSWORD"
        logger.info("✅ Password submitted.")

    async def handle_birthday(self, birthday: str):
        """Fill birthday (format: MM/DD/YYYY)."""
        logger.info("🎂 Setting birthday...")
        await self.page.wait_for_selector('select[name="birthday_day"]', timeout=5000)
        # Parse
        parts = birthday.split('/')
        if len(parts) != 3:
            raise ValueError("Birthday must be in MM/DD/YYYY format")
        month, day, year = parts
        await self.page.select('select[name="birthday_month"]', month)
        await self.page.select('select[name="birthday_day"]', day)
        await self.page.select('select[name="birthday_year"]', year)
        await self.page.click('button[type="submit"]')
        self.state = "BIRTHDAY"
        logger.info("✅ Birthday submitted.")

    async def handle_profile(self, full_name: str, username: str):
        """Fill profile details and submit."""
        logger.info(f"👤 Setting up profile: {full_name} (@{username})")
        await self.page.wait_for_selector('input[name="fullName"]', timeout=5000)
        await self.page.type('input[name="fullName"]', full_name, delay=50)
        await self.page.type('input[name="username"]', username, delay=50)
        await self.page.click('button[type="submit"]')
        self.state = "PROFILE"
        logger.info("✅ Profile submitted.")

    async def handle_terms(self):
        """Accept terms and submit."""
        logger.info("📜 Accepting terms...")
        await asyncio.sleep(1)
        # Check if there's a checkbox
        checkbox = await self.page.query_selector('input[type="checkbox"]')
        if checkbox:
            await checkbox.click()
        # Click accept/submit button
        accept_btn = await self.page.query_selector('button[type="submit"], [role="button"]:not([aria-disabled="true"])')
        if accept_btn:
            await accept_btn.click()
        self.state = "TERMS"
        logger.info("✅ Terms accepted.")

    async def wait_for_completion(self):
        """Wait for the final success screen."""
        logger.info("⏳ Waiting for completion...")
        await self.page.wait_for_function(
            """
            () => {
                const body = document.body.innerText;
                return body.includes('Welcome to Instagram') ||
                       body.includes('You\'re all set') ||
                       document.querySelector('main > div[role="button"]') !== null;
            }
            """,
            timeout=10000
        )
        self.state = "DONE"
        logger.info("🎉 Signup completed successfully!")

    async def run_signup_flow(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the entire signup flow according to the pseudo code.
        Returns a dict with 'success' and 'state'.
        """
        self.user_data = user_data
        try:
            await self.start()
            await self.open_signup_page()
            await self.wait_for_signup_form()
            await self.fill_email_and_submit(user_data['email'])
            await self.wait_for_state_change()

            # Main state machine loop
            max_attempts = 20
            attempt = 0
            while attempt < max_attempts:
                attempt += 1
                state = await self.get_current_state()
                logger.info(f"🔄 Current state: {state} (attempt {attempt}/{max_attempts})")

                if state == "OTP":
                    success = await self.handle_otp()
                    if not success:
                        return {"success": False, "state": "VERIFICATION_ERROR", "error": "OTP verification failed"}
                    # After OTP success, continue to detect next state
                    await self.wait_for_state_change()
                    continue

                elif state == "PASSWORD":
                    await self.handle_password(user_data['password'])
                    await self.wait_for_state_change()
                    continue

                elif state == "BIRTHDAY":
                    await self.handle_birthday(user_data['birthday'])
                    await self.wait_for_state_change()
                    continue

                elif state == "PROFILE":
                    await self.handle_profile(user_data['full_name'], user_data['username'])
                    await self.wait_for_state_change()
                    continue

                elif state == "TERMS":
                    await self.handle_terms()
                    await self.wait_for_state_change()
                    continue

                elif state == "SUCCESS":
                    await self.wait_for_completion()
                    return {"success": True, "state": "DONE"}

                elif state == "ERROR":
                    logger.error("❌ Error state detected.")
                    return {"success": False, "state": "ERROR", "error": "Page error"}

                elif state == "UNKNOWN":
                    logger.warning("⚠️ Unknown state. Waiting a bit...")
                    await asyncio.sleep(2)

                # If we reached max attempts without success
                if attempt >= max_attempts:
                    return {"success": False, "state": "TIMEOUT", "error": "Max attempts reached"}

            return {"success": False, "state": "TIMEOUT", "error": "Loop ended without success"}

        except Exception as e:
            logger.exception(f"❌ Exception during signup: {e}")
            return {"success": False, "state": "EXCEPTION", "error": str(e)}
        finally:
            await self.close()


# ============== Example Usage ==============
async def main():
    """Run the signup bot with given credentials."""
    # Replace with your actual data
    user = {
        "email": "your_email@example.com",
        "password": "YourSecurePassword123!",
        "birthday": "01/01/1990",   # MM/DD/YYYY
        "full_name": "John Doe",
        "username": "johndoe123"
    }

    bot = SignupBot(headless=False)  # Set to True for headless
    result = await bot.run_signup_flow(user)

    if result["success"]:
        print("✅ Signup completed successfully!")
    else:
        print(f"❌ Signup failed: {result.get('error')}")

    print(f"Final state: {result.get('state')}")


if __name__ == "__main__":
    asyncio.run(main())
