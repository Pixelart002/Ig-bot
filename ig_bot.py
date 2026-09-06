import json
import logging
import os
import re
import secrets
import string
import time
from datetime import date, timedelta
from typing import Any

import requests

from stats import record

# AI is served by the user's own Hugging Face Space running Ollama.
OLLAMA_URL = os.getenv("OLLAMA_URL", "https://vivekkumarr-my-ai.hf.space").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")
OLLAMA_API_URL = f"{OLLAMA_URL}/api/chat"
OLLAMA_TOKEN = os.getenv("OLLAMA_TOKEN") or os.getenv("HF_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _clean_json_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    # Small instruct/coder models sometimes add a short sentence before/after
    # the JSON despite the prompt. Extract the outermost JSON object safely.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return text.strip()


def ai_chat(system_prompt: str, user_prompt: str, max_tokens: int = 250) -> str | None:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.9,
            "num_predict": max_tokens,
        },
    }
    headers = {"Content-Type": "application/json"}
    if OLLAMA_TOKEN:
        headers["Authorization"] = f"Bearer {OLLAMA_TOKEN}"

    for attempt in range(4):
        try:
            response = requests.post(
                OLLAMA_API_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )

            if response.status_code >= 400:
                logging.error(
                    "Ollama HTTP %s: %s",
                    response.status_code,
                    response.text[:1500],
                )
                response.raise_for_status()

            data: dict[str, Any] = response.json()
            content = data.get("message", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Ollama returned no message content")
            return content.strip()

        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            if attempt == 3:
                logging.error("Ollama request failed: %s", exc)
                return None
            wait = min(15, 2 ** attempt)
            logging.warning("Ollama request failed; retrying in %ss: %s", wait, exc)
            time.sleep(wait)

    return None


def generate_password(length: int = 20) -> str:
    """Generate a strong unique per-account password locally; never log it or send it to the AI."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*-_" for c in password)
        ):
            return password


def generate_dob(start_year: int = 2000, end_year: int = 2008) -> str:
    """Generate a random calendar date in the requested year range."""
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    return (start + timedelta(days=secrets.randbelow((end - start).days + 1))).isoformat()


def generate_identity(theme: str = "AI, coding and technology") -> dict[str, Any] | None:
    """Generate a fresh profile identity and per-account generated metadata."""
    system_prompt = """You generate original Instagram profile identity ideas.
Return ONLY valid JSON with this exact shape:
{"display_names":["...","...","..."],"usernames":["...","...","...","...","..."],"bios":["...","...","..."]}
Rules: usernames 3-30 characters; letters, numbers, periods and underscores only; do not imitate or impersonate a real person or brand; no official-account claims; bios short and original."""
    result = ai_chat(system_prompt, f"Create a fresh profile identity around: {theme}", 300)
    if not result:
        return None
    try:
        parsed = json.loads(_clean_json_text(result))
        if not isinstance(parsed, dict):
            raise ValueError("AI returned a non-object JSON value")
        parsed["password"] = generate_password()
        parsed["date_of_birth"] = generate_dob(2000, 2008)
        record("identity_generated")
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        logging.error("AI returned invalid identity JSON: %s", exc)
        return None


def generate_caption(topic: str) -> str | None:
    return ai_chat(
        "You are a tech Instagram copywriter. Write one concise original caption. Use at most 5 relevant hashtags and do not claim affiliation with any brand.",
        f"Write a caption about: {topic}",
        160,
    )


if __name__ == "__main__":
    identity = generate_identity()
    if identity:
        print(json.dumps(identity, indent=2, ensure_ascii=False))
    else:
        raise SystemExit(1)
