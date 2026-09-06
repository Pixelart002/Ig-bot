import json
import logging
import os
import re
from typing import Any

import requests

HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct-1M")
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _clean_json_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def ai_chat(system_prompt: str, user_prompt: str, max_tokens: int = 250) -> str | None:
    if not HF_TOKEN:
        logging.error("HF_TOKEN is not configured.")
        return None

    payload = {
        "model": HF_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.9,
        "stream": False,
    }

    try:
        response = requests.post(
            HF_API_URL,
            headers={
                "Authorization": f"Bearer {HF_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError) as exc:
        logging.error("AI request failed: %s", exc)
        return None


def generate_identity(theme: str = "AI, coding and technology") -> dict[str, Any] | None:
    """Generate original name/username/bio suggestions for manual profile setup."""
    system_prompt = """You generate original Instagram profile identity ideas.
Return ONLY valid JSON with this exact shape:
{
  "display_names": ["...", "...", "..."],
  "usernames": ["...", "...", "...", "...", "..."],
  "bios": ["...", "...", "..."]
}
Rules:
- Keep usernames 3-30 characters.
- Usernames may contain letters, numbers, periods and underscores only.
- Do not imitate or impersonate a real person or brand.
- No claims of being an official account.
- Keep bios short and original.
"""
    result = ai_chat(system_prompt, f"Create a fresh profile identity around: {theme}", 300)
    if not result:
        return None
    try:
        parsed = json.loads(_clean_json_text(result))
        if not isinstance(parsed, dict):
            raise ValueError("AI returned a non-object JSON value")
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        logging.error("AI returned invalid identity JSON: %s", exc)
        return None


def generate_caption(topic: str) -> str | None:
    return ai_chat(
        "You are a tech Instagram copywriter. Write one concise original caption. "
        "Use at most 5 relevant hashtags and do not claim affiliation with any brand.",
        f"Write a caption about: {topic}",
        160,
    )


if __name__ == "__main__":
    # Generates suggestions only; account creation remains manual.
    identity = generate_identity()
    if identity:
        print(json.dumps(identity, indent=2, ensure_ascii=False))
    else:
        raise SystemExit(1)
