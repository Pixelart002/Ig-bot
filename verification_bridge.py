"""Authenticated manual verification bridge and Telegram webhook server."""
from __future__ import annotations

import base64
import hashlib
import os
import threading
from html import escape

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from browser_assist import cdp_call
from workflow import by_token, touch

app = FastAPI(title="Instagram Verification Bridge", docs_url=None, redoc_url=None)


class Point(BaseModel):
    x: float
    y: float


class TextInput(BaseModel):
    text: str


def session_for(token: str):
    session = by_token(token)
    if not session or not session.tab or not session.tab.get("webSocketDebuggerUrl"):
        raise HTTPException(status_code=404, detail="Session expired or unavailable")
    touch(session)
    return session


def ws_for(session):
    import websocket
    return websocket.create_connection(session.tab["webSocketDebuggerUrl"], timeout=15)


def telegram_webhook_secret() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/telegram/webhook")
def telegram_webhook(update: dict, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    """Receive Telegram updates through Render's single public HTTP service."""
    expected = telegram_webhook_secret()
    if not expected or x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    # Import lazily to avoid verification_bridge <-> telegram_bot import cycle.
    import telegram_bot as bot

    try:
        if "callback_query" in update:
            bot.handle_callback(update["callback_query"])
        elif "message" in update:
            bot.handle_message(update["message"])
    except Exception as exc:
        chat_id = (
            update.get("message", {}).get("chat", {}).get("id")
            or update.get("callback_query", {}).get("message", {}).get("chat", {}).get("id")
        )
        if chat_id:
            bot.audit(int(chat_id), "Webhook Error", type(exc).__name__)
    return {"ok": True}


@app.get("/v/{token}", response_class=HTMLResponse)
def page(token: str):
    session_for(token)
    safe = escape(token)
    return HTMLResponse(f"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verification Session</title>
<style>body{{font-family:system-ui;margin:0;background:#111;color:#eee;text-align:center}}header{{padding:12px}}#shot{{max-width:100%;height:auto;touch-action:none}}button{{padding:10px 14px;margin:5px;border:0;border-radius:8px}}#state{{font-size:14px;opacity:.8}}</style></head>
<body><header><b>Manual Instagram Verification</b><div id="state">Loading…</div></header>
<img id="shot" alt="Browser session">
<div><button onclick="refresh()">↻ Refresh</button><button onclick="window.close()">Close</button></div>
<p>Complete CAPTCHA/OTP/verification yourself. This bridge does not solve or bypass it.</p>
<script>
const t='{safe}'; const img=document.getElementById('shot'); const state=document.getElementById('state');
async function refresh(){{
  const s=await fetch('/v/'+t+'/state').then(r=>r.json()); state.textContent=s.status+' · '+s.url;
  const b=await fetch('/v/'+t+'/screenshot').then(r=>r.json()); img.src='data:image/png;base64,'+b.image;
}}
img.addEventListener('click',async e=>{{const r=img.getBoundingClientRect(); const x=e.offsetX*img.naturalWidth/r.width; const y=e.offsetY*img.naturalHeight/r.height; await fetch('/v/'+t+'/click',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{x,y}})}}); setTimeout(refresh,300);}});
window.addEventListener('keydown',async e=>{{if(e.key.length===1) await fetch('/v/'+t+'/text',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{text:e.key}})}}); else if(e.key==='Enter') await fetch('/v/'+t+'/key?key=Enter',{{method:'POST'}}); setTimeout(refresh,150);}});
refresh(); setInterval(refresh,2500);
</script></body></html>""")


@app.get("/v/{token}/state")
def state(token: str):
    session = session_for(token)
    ws = ws_for(session)
    try:
        result = cdp_call(ws, "Runtime.evaluate", {"expression": "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,1200)})", "returnByValue": True})
        value = result.get("result", {}).get("result", {}).get("value", "{}")
        import json
        data = json.loads(value)
        text = data.get("text", "").lower()
        if any(x in text for x in ("security code", "confirmation code", "enter the code", "captcha", "confirm your email")):
            status = "verification_required"
        elif "welcome to instagram" in text:
            status = "completed"
        else:
            status = session.status
        session.status = status
        return {"status": status, "url": data.get("url", ""), "title": data.get("title", "")}
    finally:
        ws.close()


@app.get("/v/{token}/screenshot")
def screenshot(token: str):
    session = session_for(token)
    ws = ws_for(session)
    try:
        result = cdp_call(ws, "Page.captureScreenshot", {"format": "png"})
        image = result.get("result", {}).get("data")
        if not image:
            raise HTTPException(status_code=502, detail="Screenshot unavailable")
        return {"image": image}
    finally:
        ws.close()


@app.post("/v/{token}/click")
def click(token: str, point: Point):
    session = session_for(token)
    ws = ws_for(session)
    try:
        cdp_call(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": point.x, "y": point.y, "button": "left", "clickCount": 1})
        cdp_call(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": point.x, "y": point.y, "button": "left", "clickCount": 1}, request_id=2)
        return {"ok": True}
    finally:
        ws.close()


@app.post("/v/{token}/text")
def text(token: str, body: TextInput):
    if len(body.text) > 200:
        raise HTTPException(status_code=400, detail="Input too long")
    session = session_for(token)
    ws = ws_for(session)
    try:
        cdp_call(ws, "Input.insertText", {"text": body.text})
        return {"ok": True}
    finally:
        ws.close()


@app.post("/v/{token}/key")
def key(token: str, key: str):
    allowed = {"Enter", "Tab", "Backspace", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"}
    if key not in allowed:
        raise HTTPException(status_code=400, detail="Key not allowed")
    session = session_for(token)
    ws = ws_for(session)
    try:
        cdp_call(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        cdp_call(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key}, request_id=2)
        return {"ok": True}
    finally:
        ws.close()


def start_bridge() -> None:
    host = os.getenv("VERIFICATION_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("VERIFICATION_PORT", "8080")))
    threading.Thread(target=lambda: uvicorn.run(app, host=host, port=port, log_level="warning"), daemon=True).start()
