# Ig-bot

Lightweight Python utility for generating original Instagram profile ideas and captions with Hugging Face Inference Providers.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HF_TOKEN='your_token'
python ig_bot.py
```

Optional model override:

```bash
export HF_MODEL='Qwen/Qwen2.5-7B-Instruct-1M'
```

## Output

`ig_bot.py` generates:
- display-name suggestions
- username suggestions
- short bios
- reusable tech captions

Instagram account creation, CAPTCHA, OTP, and verification remain manual. The project does not implement verification bypass or anti-bot evasion.

## Security

Never commit `HF_TOKEN`. Keep it in the environment or your hosting provider's secret store. `.env` files are ignored by Git.
