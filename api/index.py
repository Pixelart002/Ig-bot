from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import os

app = FastAPI(title="IG Bot Vercel Bridge", docs_url=None, redoc_url=None)


@app.get("/api")
def api_root():
    return {
        "ok": True,
        "service": "ig-bot",
        "runtime": "vercel-python",
        "message": "Vercel API is online",
    }


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "ig-bot",
        "runtime": "vercel-python",
        "telegram_worker": "external",
        "lightpanda": "external",
    }


@app.get("/api/bridge")
def bridge():
    """Return the externally hosted verification bridge URL when configured.

    The Lightpanda/CDP session itself must remain on the long-running browser
    service; Vercel only provides the public API/status surface.
    """
    bridge_url = os.getenv("VERIFICATION_SERVICE_URL", "").rstrip("/")
    if bridge_url:
        return RedirectResponse(url=bridge_url, status_code=307)
    return {
        "ok": False,
        "message": "Verification bridge is hosted separately with the Lightpanda worker.",
        "configured": False,
    }
