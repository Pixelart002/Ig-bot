"""Authenticated manual verification bridge and Telegram webhook server."""
from __future__ import annotations

import hashlib
import json
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
    tab = session.tab if session else None
    if not session or not tab or not tab.get("_ws") or not tab.get("sessionId"):
        raise HTTPException(status_code=404, detail="Session expired or unavailable")
    touch(session)
    return session


def ws_for(session):
    """Use the live browser-level CDP websocket owned by browser_assist."""
    tab = session.tab or {}
    ws = tab.get("_ws")
    session_id = tab.get("sessionId")
    if ws is None or not session_id:
        raise HTTPException(status_code=404, detail="Browser CDP session unavailable")
    return ws, session_id


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
    """Render the live Lightpanda Instagram viewport, not a second browser session."""
    session_for(token)
    safe = escape(token)
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Instagram</title>
<style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#fff}}
body{{font-family:system-ui,-apple-system,sans-serif;display:flex;flex-direction:column}}
#browser{{position:relative;flex:1;min-height:0;background:#fff;display:flex;align-items:center;justify-content:center}}
#shot{{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;touch-action:none;user-select:none;-webkit-user-drag:none}}
#bar{{position:fixed;left:0;right:0;bottom:0;z-index:5;display:flex;align-items:center;gap:8px;padding:8px 10px;padding-bottom:calc(8px + env(safe-area-inset-bottom));background:rgba(0,0,0,.78);color:#fff;font-size:12px;backdrop-filter:blur(8px)}}
#state{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;opacity:.9}}
button{{border:0;border-radius:7px;padding:7px 10px;background:#fff;color:#111;font-weight:600}}
#hint{{position:absolute;top:8px;left:50%;transform:translateX(-50%);z-index:4;padding:5px 9px;border-radius:999px;background:rgba(0,0,0,.65);color:#fff;font-size:11px;pointer-events:none;opacity:.85}}
</style></head>
<body>
<div id="browser"><div id="hint">Live Instagram session</div><img id="shot" alt="Live Instagram browser page"></div>
<div id="bar"><span id="state">Loading Instagram…</span><button onclick="refresh()">↻</button></div>
<script>
const t='{safe}';
const img=document.getElementById('shot');
const state=document.getElementById('state');
let busy=false;
async function json(url, options){{const r=await fetch(url, options); if(!r.ok) throw new Error(await r.text()); return r.json();}}
async function refresh(){{
  if(busy) return;
  busy=true;
  try{{
    const s=await json('/v/'+t+'/state');
    state.textContent=(s.url || 'Instagram')+' · '+s.status;
    const b=await json('/v/'+t+'/screenshot');
    img.src='data:image/png;base64,'+b.image;
  }}catch(e){{state.textContent='Session unavailable';}}
  finally{{busy=false;}}
}}
img.addEventListener('click',async e=>{{
  const r=img.getBoundingClientRect();
  if(!img.naturalWidth || !img.naturalHeight) return;
  const x=(e.clientX-r.left)*img.naturalWidth/r.width;
  const y=(e.clientY-r.top)*img.naturalHeight/r.height;
  try{{await json('/v/'+t+'/click',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{x,y}})}});}}catch(_e){{}}
  setTimeout(refresh,250);
}});
window.addEventListener('keydown',async e=>{{
  if(e.key.length===1){{try{{await json('/v/'+t+'/text',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{text:e.key}})}});}}catch(_e){{}}}}
  else if(e.key==='Enter'){{try{{await json('/v/'+t+'/key?key=Enter',{{method:'POST'}});}}catch(_e){{}}}}
  else if(e.key==='Backspace'){{try{{await json('/v/'+t+'/key?key=Backspace',{{method:'POST'}});}}catch(_e){{}}}}
  setTimeout(refresh,120);
}});
refresh();
setInterval(refresh,2500);
</script></body></html>""")


@app.get("/v/{token}/state")
def state(token: str):
    session = session_for(token)
    ws, session_id = ws_for(session)
    result = cdp_call(
        ws,
        "Runtime.evaluate",
        {"expression": "JSON.stringify({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,1200)})", "returnByValue": True},
        session_id=session_id,
    )
    value = result.get("result", {}).get("result", {}).get("value", "{}")
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


@app.get("/v/{token}/screenshot")
def screenshot(token: str):
    session = session_for(token)
    ws, session_id = ws_for(session)
    result = cdp_call(ws, "Page.captureScreenshot", {"format": "png"}, session_id=session_id)
    image = result.get("result", {}).get("data")
    if not image:
        raise HTTPException(status_code=502, detail="Screenshot unavailable")
    return {"image": image}


@app.post("/v/{token}/click")
def click(token: str, point: Point):
    session = session_for(token)
    ws, session_id = ws_for(session)
    cdp_call(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": point.x, "y": point.y, "button": "left", "clickCount": 1}, session_id=session_id)
    cdp_call(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": point.x, "y": point.y, "button": "left", "clickCount": 1}, request_id=2, session_id=session_id)
    return {"ok": True}


@app.post("/v/{token}/text")
def text(token: str, body: TextInput):
    if len(body.text) > 200:
        raise HTTPException(status_code=400, detail="Input too long")
    session = session_for(token)
    ws, session_id = ws_for(session)
    cdp_call(ws, "Input.insertText", {"text": body.text}, session_id=session_id)
    return {"ok": True}


@app.post("/v/{token}/key")
def key(token: str, key: str):
    allowed = {"Enter", "Tab", "Backspace", "Escape", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"}
    if key not in allowed:
        raise HTTPException(status_code=400, detail="Key not allowed")
    session = session_for(token)
    ws, session_id = ws_for(session)
    cdp_call(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": key}, session_id=session_id)
    cdp_call(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": key}, request_id=2, session_id=session_id)
    return {"ok": True}


def start_bridge() -> None:
    host = os.getenv("VERIFICATION_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("VERIFICATION_PORT", "8080")))
    threading.Thread(target=lambda: uvicorn.run(app, host=host, port=port, log_level="warning"), daemon=True).start()
