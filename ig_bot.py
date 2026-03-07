import time
import schedule
import os
import json
import random
import shutil
import logging
import urllib.request
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

# ==========================================
# ⚙️ SYSTEM CONFIGURATION
# ==========================================
IG_USERNAME = os.getenv("IG_USERNAME", "YOUR_INSTAGRAM_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD", "YOUR_INSTAGRAM_PASSWORD")
SESSION_FILE = "ig_session.json"
PERSONA_FLAG = "persona_setup.done" # Isse pata chalega ki DP aur Bio lag chuka hai

HF_TOKEN = os.getenv("HF_TOKEN", "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")
HF_TEXT_API = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-Coder-32B-Instruct/v1/chat/completions"
HF_IMAGE_API = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

PENDING_FOLDER = "pending_posts"
ARCHIVE_FOLDER = "posted_archive"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("ig_bot.log"), logging.StreamHandler()]
)

os.makedirs(PENDING_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# ==========================================
# 🧠 AI BRAIN: TEXT GENERATOR
# ==========================================
def get_ai_brain_response(system_prompt, user_prompt, max_tokens=150):
    payload = {
        "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.8 
    }
    req = urllib.request.Request(
        HF_TEXT_API, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode('utf-8'))
            text = res['choices'][0]['message']['content'].strip()
            return text.replace("```json", "").replace("```", "").strip()
    except Exception as e:
        logging.error(f"⚠️ AI Text Error: {e}")
        return None

# ==========================================
# 🎨 AI ARTIST: IMAGE GENERATOR
# ==========================================
def generate_ai_image(prompt, save_path):
    logging.info(f"🎨 AI Artist photo bana raha hai: '{prompt[:50]}...'")
    # 🔥 Coding/hacker aesthetic modifiers
    payload = {"inputs": prompt + ", cyberpunk, neon lights, highly detailed, 8k, masterpiece, unreal engine 5 render"}
    
    req = urllib.request.Request(
        HF_IMAGE_API, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {HF_TOKEN}'},
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            image_bytes = r.read()
            with open(save_path, "wb") as f:
                f.write(image_bytes)
            logging.info(f"🖼️ Photo successfully save ho gayi: {save_path}")
            return True
    except Exception as e:
        logging.error(f"🛑 Image Generation Error: {e}")
        return False

# ==========================================
# 🤖 AUTO PERSONA SETUP (DP & BIO)
# ==========================================
def setup_ai_persona(cl):
    logging.info("🤖 AI Coder Persona Setup shuru ho raha hai...")
    
    # 1. Generate & Set Bio
    bio_sys_prompt = "You are the manager for an autonomous AI that writes code. Create a short, edgy, futuristic Instagram bio. Max 100 characters. 1-2 emojis max. No hashtags."
    bio = get_ai_brain_response(bio_sys_prompt, "Write my Instagram bio.")
    if bio:
        try:
            cl.account_edit_profile(biography=bio)
            logging.info(f"✅ Bio set to: {bio}")
        except Exception as e:
            logging.error(f"⚠️ Bio update failed: {e}")

    # 2. Generate & Set Profile Picture (Avatar)
    avatar_path = "ai_avatar.jpg"
    avatar_prompt = "A futuristic cyberpunk hacker AI robot portrait, glowing neon blue eyes, wearing a hoodie, binary code matrix background, hyperrealistic portrait"
    
    if generate_ai_image(avatar_prompt, avatar_path):
        try:
            cl.account_change_picture(avatar_path)
            logging.info("✅ Profile Picture (DP) update ho gayi!")
        except Exception as e:
            logging.error(f"⚠️ Profile picture update failed: {e}")
            
    # Flag save kardo taaki roz DP change na kare
    with open(PERSONA_FLAG, "w") as f:
        f.write("Setup complete.")

# ==========================================
# 💻 CONTENT STRATEGY (CODING NICHE)
# ==========================================
def generate_viral_concept():
    logging.info("🧠 AI se aaj ki Coding/Hacker post ka Idea le rahe hain...")
    sys_prompt = "You are a creative director for a tech and coding Instagram page. Generate a 1-sentence description for a beautiful, futuristic, or relatable image about programming, artificial intelligence, cyberpunk hackers, or computer setups. Respond ONLY with the image description."
    idea = get_ai_brain_response(sys_prompt, "Give me a fresh image idea for a coding page.")
    return idea if idea else "A sleek futuristic programming setup with multiple glowing monitors showing Python code in a dark room"

def generate_viral_caption(topic):
    logging.info("✍️ Caption likh rahe hain...")
    sys_prompt = "You are an expert tech Instagram influencer. Write a short, engaging caption for a post about the given topic. Include 5-7 highly relevant hashtags like #coding #ai #python #developer. Respond ONLY with the caption."
    caption = get_ai_brain_response(sys_prompt, f"Topic: {topic}")
    return caption if caption else "Building the future, one line of code at a time. 💻✨ #coding #ai #developer #python #tech"

# ==========================================
# 🛡️ ANTI-BAN & LOGIN LOGIC
# ==========================================
def login_and_warmup():
    cl = Client()
    cl.delay_range = [3, 7] # Thoda safe delay

    try:
        if os.path.exists(SESSION_FILE):
            logging.info("🔓 Purane session se login try kar rahe hain...")
            cl.load_settings(SESSION_FILE)
            cl.login(IG_USERNAME, IG_PASSWORD)
            try:
                cl.get_timeline_feed()
            except LoginRequired:
                logging.warning("⚠️ Session expire ho gaya, naya login kar rahe hain...")
                cl.login(IG_USERNAME, IG_PASSWORD, relogin=True)
                cl.dump_settings(SESSION_FILE)
        else:
            logging.info("🔐 First-time fresh login kar rahe hain...")
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(SESSION_FILE)
            logging.info("✅ Naya Session save ho gaya!")

        # 🔥 PERSONA SETUP CHECK
        if not os.path.exists(PERSONA_FLAG):
            setup_ai_persona(cl)

        logging.info("🔥 Account Warmup: Feed scroll kar rahe hain...")
        feed = cl.get_timeline_feed()
        if feed:
            post_to_like = random.choice(feed[:3])
            cl.media_like(post_to_like.id)
            logging.info("👍 Ek random timeline post like ki (Anti-ban warmup).")
            time.sleep(random.uniform(2, 5))

        return cl

    except Exception as e:
        logging.error(f"🛑 Login Error: {e}")
        return None

# ==========================================
# 🚀 THE FULLY AUTOMATED WORKFLOW
# ==========================================
def automated_posting_job():
    delay_minutes = random.randint(1, 15)
    logging.info(f"⏳ Anti-Bot: {delay_minutes} minute baad automation shuru hoga...")
    time.sleep(delay_minutes * 60)

    logging.info("🚀 FULL AUTOMATION SEQUENCE INITIATED!")
    
    post_idea = generate_viral_concept()
    
    image_filename = f"ai_coder_post_{int(time.time())}.jpg"
    image_path = os.path.join(PENDING_FOLDER, image_filename)
    
    success = generate_ai_image(post_idea, image_path)
    if not success:
        logging.error("❌ Photo nahi ban paayi. Job aborted.")
        return
        
    caption = generate_viral_caption(post_idea)

    cl = login_and_warmup()
    if not cl:
        logging.error("❌ Login fail ho gaya, posting cancel.")
        return

    try:
        logging.info("📤 Uploading Photo to Instagram...")
        media = cl.photo_upload(image_path, caption)
        logging.info(f"✅ BINGO! Photo post ho gayi. Link: https://instagram.com/p/{media.code}/")
        
        archive_path = os.path.join(ARCHIVE_FOLDER, image_filename)
        shutil.move(image_path, archive_path)
        logging.info(f"📁 Photo ko Archive mein move kar diya.")
        
    except Exception as e:
        logging.error(f"🛑 Posting upload mein error: {e}")

# ==========================================
# ⏰ 24/7 SCHEDULER
# ==========================================
def start_bot():
    logging.info("==========================================")
    logging.info("🤖 AI CODER IG EMPIRE BOT STARTED (24/7)")
    logging.info("==========================================")
    
    # Rozana 2 posts ka schedule
    schedule.every().day.at("10:00").do(automated_posting_job)
    schedule.every().day.at("18:30").do(automated_posting_job)
    
    # 🔥 Pehli baar test karne ke liye ye uncomment karein:
    # automated_posting_job()

    while True:
        try:
            schedule.run_pending()
            time.sleep(60) 
        except KeyboardInterrupt:
            logging.info("🛑 Bot manually stopped.")
            break
        except Exception as e:
            logging.error(f"⚠️ Scheduler Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    start_bot()