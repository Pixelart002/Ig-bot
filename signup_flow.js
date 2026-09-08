#!/usr/bin/env node

const { CDP } = require('lightpanda-cdp');  // npm install lightpanda-cdp

// ---------- Logging ----------
const log = (msg) => console.log(`[${new Date().toISOString()}] ${msg}`);

// ---------- Sleep helper ----------
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// ---------- Main signup flow ----------
async function runSignup(userData) {
    const { email, password, birthday, full_name, username } = userData;
    let browser, page;
    let state = 'INIT';

    try {
        // START: Launch browser (headless = false so user can see OTP)
        log('🚀 Starting browser...');
        browser = await CDP.launch({
            headless: false,   // OTP ke liye visible rakhna zaroori hai
            args: ['--no-sandbox', '--disable-dev-shm-usage']
        });
        page = await browser.newPage();
        log('✅ Browser launched.');

        // OPEN signup page
        log('🌐 Opening signup page...');
        await page.goto('https://www.instagram.com/accounts/emailsignup/', {
            waitUntil: 'networkidle2',
            timeout: 30000
        });
        state = 'PAGE_LOADED';

        // WAIT until signup form is ready
        log('⏳ Waiting for form...');
        await page.waitForSelector('input[name="emailOrPhone"]', { timeout: 10000 });
        state = 'FORM_READY';

        // FILL email & SUBMIT
        log(`📧 Filling email: ${email}`);
        await page.type('input[name="emailOrPhone"]', email, { delay: 50 });
        await sleep(1000);
        await page.click('button[type="submit"]');
        state = 'EMAIL_SUBMITTED';
        log('✅ Email submitted.');

        // ---- State machine loop ----
        let maxAttempts = 20;
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            await sleep(2000); // wait for page to settle
            const content = await page.content();
            let currentState = 'UNKNOWN';

            // Detect state
            if (content.includes('Enter the code') || content.includes('Confirmation Code') ||
                await page.$('input[name="verificationCode"]')) {
                currentState = 'OTP';
            } else if (await page.$('input[name="password"]')) {
                currentState = 'PASSWORD';
            } else if (content.includes('Date of birth') || await page.$('select[name="birthday_day"]')) {
                currentState = 'BIRTHDAY';
            } else if (content.includes('Create a profile') || content.includes('Add a profile') ||
                       await page.$('input[name="fullName"]')) {
                currentState = 'PROFILE';
            } else if (content.includes('Terms and Conditions') || content.includes('Accept terms')) {
                currentState = 'TERMS';
            } else if (content.includes('Welcome to Instagram') || content.includes("You're all set") ||
                       await page.$('main > div[role="button"]')) {
                currentState = 'SUCCESS';
            } else if (content.includes('Sorry, this page') || content.includes('Try again')) {
                currentState = 'ERROR';
            }

            log(`🔄 Attempt ${attempt+1}/${maxAttempts} → State: ${currentState}`);

            // ----- Handle each state -----
            if (currentState === 'OTP') {
                state = 'WAITING_FOR_OTP';
                log('📱 OTP required. Please enter the code manually in the browser and submit.');
                log('⏳ Waiting for verification (max 5 minutes)...');
                // Wait until page changes (password / profile / success)
                await page.waitForFunction(
                    () => {
                        const body = document.body.innerText;
                        return body.includes('Password') ||
                               body.includes('Create a profile') ||
                               document.querySelector('input[type="password"]') !== null ||
                               body.includes('Welcome to Instagram');
                    },
                    { timeout: 300000 } // 5 min
                );
                log('✅ OTP verification succeeded (or page changed).');
                continue;   // loop will detect next state
            }

            if (currentState === 'PASSWORD') {
                state = 'PASSWORD';
                log('🔑 Setting password...');
                await page.type('input[name="password"]', password, { delay: 50 });
                await page.click('button[type="submit"]');
                log('✅ Password submitted.');
                continue;
            }

            if (currentState === 'BIRTHDAY') {
                state = 'BIRTHDAY';
                log('🎂 Setting birthday...');
                const parts = birthday.split('/');
                if (parts.length !== 3) throw new Error('Birthday must be MM/DD/YYYY');
                const [month, day, year] = parts;
                await page.select('select[name="birthday_month"]', month);
                await page.select('select[name="birthday_day"]', day);
                await page.select('select[name="birthday_year"]', year);
                await page.click('button[type="submit"]');
                log('✅ Birthday submitted.');
                continue;
            }

            if (currentState === 'PROFILE') {
                state = 'PROFILE';
                log(`👤 Setting profile: ${full_name} (@${username})`);
                await page.type('input[name="fullName"]', full_name, { delay: 50 });
                await page.type('input[name="username"]', username, { delay: 50 });
                await page.click('button[type="submit"]');
                log('✅ Profile submitted.');
                continue;
            }

            if (currentState === 'TERMS') {
                state = 'TERMS';
                log('📜 Accepting terms...');
                const chk = await page.$('input[type="checkbox"]');
                if (chk) await chk.click();
                const btn = await page.$('button[type="submit"], [role="button"]');
                if (btn) await btn.click();
                log('✅ Terms accepted.');
                continue;
            }

            if (currentState === 'SUCCESS') {
                state = 'DONE';
                log('🎉 Signup completed successfully!');
                return { success: true, state: 'DONE' };
            }

            if (currentState === 'ERROR') {
                log('❌ Error state detected.');
                return { success: false, state: 'ERROR', error: 'Page error' };
            }

            // UNKNOWN – continue waiting
            if (attempt === maxAttempts - 1) {
                return { success: false, state: 'TIMEOUT', error: 'Max attempts reached' };
            }
        }

        return { success: false, state: 'TIMEOUT', error: 'Loop ended without success' };

    } catch (error) {
        log(`❌ Exception: ${error.message}`);
        return { success: false, state: 'EXCEPTION', error: error.message };
    } finally {
        if (browser) {
            await browser.close();
            log('🔒 Browser closed.');
        }
    }
}

// ---------- Entry point ----------
(async () => {
    // Accept user data as JSON string from command line argument
    const args = process.argv.slice(2);
    if (args.length === 0) {
        console.error('Usage: node signup_flow.js \'{"email":"...","password":"...", ...}\'');
        process.exit(1);
    }
    let userData;
    try {
        userData = JSON.parse(args[0]);
    } catch (e) {
        console.error('Invalid JSON input');
        process.exit(1);
    }

    const result = await runSignup(userData);
    // Output ONLY the JSON result (so Python can parse it)
    console.log(JSON.stringify(result));
})();
